"""Dry-run de la escalera sobre el corpus real (ticket T10) — SOLO MIDE.

- Rungs 1–2 (texto + raster/QR); VLM local y cloud quedan como `skipped`
  (no configurados en el dry-run): degradan, nunca abortan (AGENTS.md §3).
- Idempotente: la misma disciplina de cache por página que T1; re-ejecutar un
  lote completado es un no-op que reutiliza evidencia (AGENTS.md §5).
- Concurrencia ≤ 2 archivos en vuelo; timeout por archivo ⇒ registrar y seguir.
- El dry-run NO decide resultados: solo mide extracción.

Uso:
    uv run python -m albertitos.extract.dryrun \
        --corpus caja-de-alberto/facturas --out .sdd/metrics/corpus-dryrun.json \
        [--limit N] [--only GLOB] [--workers 2] [--timeout 30]
"""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean

from albertitos.extract import ExtractionConfig, ExtractionLadder

CORPUS_FALLBACKS = (
    "caja-de-alberto/facturas",
    "/home/deploy/hackspain26/caja-de-alberto/facturas",
)

# rungs 3–5 fuera del dry-run: su ausencia degrada, no aborta
_DRYRUN_CFG = {
    "tesseract_bin": "/nonexistent/tesseract",  # ⇒ skipped:tesseract-not-on-PATH
    "vlm_base_url": "http://127.0.0.1:1",  # ⇒ skipped:llama-server-not-running
}

TIMEOUT_ROUTE = "timeout"
ERROR_ROUTE = "error"


@dataclass
class DryRunOptions:
    corpus_dir: Path
    out_path: Path
    evidence_path: Path | None = None
    cache_root: Path = Path(".sdd/cache/dryrun")
    max_workers: int = 2  # regla dura T10: ≤ 2 archivos en vuelo
    per_file_timeout_s: float = 30.0
    limit: int | None = None
    only: str | None = None  # glob sobre el nombre de archivo


@dataclass
class FileResult:
    file_id: str
    route: str  # rung1_pdf_text | rung2_qr_only | raster_no_qr | error | timeout
    n_pages: int
    error: str = ""
    page_routes: list[str] = field(default_factory=list)


def _classify_page(page) -> str:
    if page.final_rung == "rung1_pdf_text":
        return "rung1_pdf_text"
    if page.qr_only:
        return "rung2_qr_only"
    return "raster_no_qr"


def _classify_file(res: list, error: str, name: str = "") -> FileResult:
    if not res:
        return FileResult(file_id=name, route=ERROR_ROUTE, n_pages=0, error=error or "no-pages")
    page_routes = [_classify_page(p) for p in res]
    if all(r == "rung1_pdf_text" for r in page_routes):
        route = "rung1_pdf_text"  # todas las páginas con capa de texto usable
    elif any(r == "rung2_qr_only" for r in page_routes):
        route = "rung2_qr_only"
    elif any(r == "rung1_pdf_text" for r in page_routes):
        route = "mixed"  # algunas páginas con texto, otras caen a raster
    else:
        route = "raster_no_qr"
    return FileResult(
        file_id=name,
        route=route,
        n_pages=len(res),
        page_routes=page_routes,
    )


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = min(len(s) - 1, max(0, round(q * (len(s) - 1))))
    return round(float(s[idx]), 1)


def _latency_stats(values: list[int]) -> dict:
    if not values:
        return {"n": 0, "mean_ms": None, "p95_ms": None}
    return {
        "n": len(values),
        "mean_ms": round(mean(values), 1),
        "p95_ms": _percentile([float(v) for v in values], 0.95),
    }


def _cached_latencies(cache_root: Path, engine: str) -> list[int]:
    """Latencias medidas (ms) de cada página para un rung, desde el cache.

    Viven en la feature cacheada: re-ejecutar NO las re-mide, de modo que las
    métricas de una corrida repetida son idénticas (0 re-procesos).
    """
    out: list[int] = []
    for path in sorted(Path(cache_root).rglob("*.json")):
        if f"-{engine}-" not in path.name:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for feat in payload.get("features", []):
            if feat.get("type") in ("pdf_text", "page_image"):
                out.append(int(feat.get("latency_ms", 0)))
    return out


def run_dryrun(opts: DryRunOptions) -> dict:
    """Corre la escalera (rungs 1–2) sobre el corpus y escribe las métricas."""
    # regla dura T10: concurrencia ≤ 2 archivos en vuelo
    max_workers = max(1, min(2, opts.max_workers))
    opts.max_workers = max_workers
    corpus = Path(opts.corpus_dir)
    if not corpus.is_dir():
        raise FileNotFoundError(f"corpus no encontrado: {corpus}")
    files = sorted(p for p in corpus.glob("*.pdf") if p.is_file())
    if opts.only:
        import fnmatch

        files = [f for f in files if fnmatch.fnmatch(f.name, opts.only)]
    if opts.limit is not None:
        files = files[: opts.limit]

    cfg = ExtractionConfig(**_DRYRUN_CFG)
    ladder = ExtractionLadder(
        cfg=cfg,
        cache_root=opts.cache_root,
        evidence_path=opts.evidence_path,
    )

    results: list[FileResult] = []
    t0 = time.monotonic()

    def process(pdf_path: Path) -> FileResult:
        try:
            pages = ladder.extract_file(pdf_path)
            return _classify_file(pages, "", pdf_path.name)
        except Exception as exc:  # noqa: BLE001 - un archivo roto nunca para el lote
            return FileResult(file_id=pdf_path.name, route=ERROR_ROUTE, n_pages=0, error=str(exc))

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pdf: pool.submit(process, pdf) for pdf in files}
        for pdf, fut in futures.items():
            try:
                res = fut.result(timeout=opts.per_file_timeout_s)
            except FuturesTimeout:
                res = FileResult(
                    file_id=pdf.name, route=TIMEOUT_ROUTE, n_pages=0,
                    error=f"timeout>{opts.per_file_timeout_s}s",
                )
            except Exception as exc:  # noqa: BLE001 - registrar y seguir
                res = FileResult(file_id=pdf.name, route=ERROR_ROUTE, n_pages=0, error=str(exc))
            results.append(res)

    wall_seconds = round(time.monotonic() - t0, 2)

    # ---- métricas desde features (la latencia cacheada se conserva en la feature)
    from collections import Counter

    routes = Counter(r.route for r in results)
    n_files = len(results)

    usable_files = sum(1 for r in results if r.route in ("rung1_pdf_text", "mixed"))

    # latencias medidas por rung, desde el cache de páginas: re-ejecutar conserva
    # la medida original (idempotencia byte a byte, 0 re-procesos)
    lat_rung1 = _cached_latencies(opts.cache_root, "pdf_text")
    lat_rung2 = _cached_latencies(opts.cache_root, "raster_qr")
    errors: list[FileResult] = [r for r in results if r.route in (ERROR_ROUTE, TIMEOUT_ROUTE)]
    r1_s = sum(lat_rung1) / 1000.0
    metrics = {
        "kind": "corpus-dryrun",
        "wall_seconds": wall_seconds,
        "config_version": cfg.config_version,
        "corpus_dir": str(corpus),
        "n_files": n_files,
        "rutas": {
            "rung1_pdf_text": routes.get("rung1_pdf_text", 0),
            "mixed": routes.get("mixed", 0),
            "rung2_qr_only": routes.get("rung2_qr_only", 0),
            "raster_no_qr": routes.get("raster_no_qr", 0),
            "error": routes.get(ERROR_ROUTE, 0),
            "timeout": routes.get(TIMEOUT_ROUTE, 0),
        },
        "rung1_pdf_text": {
            "archivos_con_texto_usable": usable_files,
            "latencia": _latency_stats(lat_rung1),
        },
        "rung2_raster_qr": {
            "latencia": _latency_stats(lat_rung2),
        },
        "rung1_files_per_s": round(len(lat_rung1) / r1_s, 3) if r1_s > 0 else None,
        "fallos": [
            {"file_id": r.file_id, "ruta": r.route, "causa": r.error} for r in errors
        ],
        "concurrencia_max": opts.max_workers,
        "timeout_por_archivo_s": opts.per_file_timeout_s,
    }
    assert sum(metrics["rutas"].values()) == n_files, "las rutas deben cuadrar con el total"

    opts.out_path.parent.mkdir(parents=True, exist_ok=True)
    opts.out_path.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return metrics


def main() -> None:
    ap = argparse.ArgumentParser(description="Dry-run de la escalera (T10)")
    ap.add_argument("--corpus", default=None, help="directorio de PDFs (solo lectura)")
    ap.add_argument("--out", default=".sdd/metrics/corpus-dryrun.json")
    ap.add_argument("--evidence", default=".sdd/metrics/evidence-dryrun.jsonl")
    ap.add_argument("--cache-root", default=".sdd/cache/dryrun")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--only", default=None)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--timeout", type=float, default=30.0)
    args = ap.parse_args()

    corpus = args.corpus
    if corpus is None:
        for cand in CORPUS_FALLBACKS:
            if Path(cand).is_dir():
                corpus = cand
                break
    if corpus is None:
        raise SystemExit("corpus no encontrado; pasa --corpus")

    metrics = run_dryrun(
        DryRunOptions(
            corpus_dir=Path(corpus),
            out_path=Path(args.out),
            evidence_path=Path(args.evidence),
            cache_root=Path(args.cache_root),
            max_workers=max(1, min(2, args.workers)),  # regla dura: ≤ 2
            per_file_timeout_s=args.timeout,
            limit=args.limit,
            only=args.only,
        )
    )
    print(json.dumps(metrics["rutas"], ensure_ascii=False))


if __name__ == "__main__":
    main()
