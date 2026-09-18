"""Calibración de los umbrales del rung 3 con datos MEDIDOS (ticket T10, ADR D-001).

Metodología:
1. Del dry-run (`.sdd/metrics/evidence-dryrun.jsonl`) saca las páginas que
   cayeron al rung 2 (capa de texto inutil) — son las que llegan al rung 3.
2. Las OCR-a con el MISMO motor de tesseract que usa el rung 3
   (libtesseract 5.5.1 vía tesserocr — binario no instalado en PATH; ver
   notas en calibracion.md) y mide las DOS partes del gate:
   word-conf (media ponderada por longitud) + cobertura de campos esperados.
3. Mide también la cobertura de campos de las capas de texto usables del
   corpus (referencia de lo que una página "buena" alcanza).
4. Elige umbrales que separen legibles de ilegibles, citando qué % del corpus
   queda por encima/debajo de cada uno. Nada de números mágicos.

Uso (tras el dry-run):
    uv run --no-sync python tools/calibrate_rung3.py \
        --evidence .sdd/metrics/evidence-dryrun.jsonl \
        --cache-root .sdd/cache/dryrun \
        --tessdata .sdd/tessdata \
        --out .sdd/metrics/calibracion
"""

from __future__ import annotations

import json
from pathlib import Path
from statistics import mean

from albertitos.extract.config import ExtractionConfig
from albertitos.extract.rungs import field_coverage

DEFAULT_OUT = Path(".sdd/metrics/calibracion")


def _percentiles(values: list[float], qs=(0.05, 0.25, 0.5, 0.75, 0.95)) -> dict:
    if not values:
        return {}
    s = sorted(values)
    return {f"p{int(q*100)}": round(s[min(len(s) - 1, round(q * (len(s) - 1)))], 2) for q in qs}


def _load_rung1_pages(evidence_path: Path) -> tuple[list[dict], list[dict]]:
    """Páginas del dry-run: (rechazadas en rung1, aceptadas en rung1)."""
    reject, accept = [], []
    with Path(evidence_path).open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            if "rung1" not in row.get("stage", ""):
                continue
            if row["outcome"] == "reject":
                reject.append(row)
            elif row["outcome"] == "accept":
                accept.append(row)
    return reject, accept


def _ocr_page(png_path: Path, tessdata: Path, lang: str) -> tuple[float, float, int]:
    """OCR de una página → (word_conf ponderada por longitud, cobertura, n_palabras).

    Misma definición de word-conf que `run_tesseract` (rungs.py): media de
    confianzas de palabra ponderada por longitud.
    """
    # usamos el PNG cacheado del dry-run (mismo render que el rung 3)
    import cv2
    from PIL import Image
    from tesserocr import PSM, RIL, PyTessBaseAPI

    from albertitos.extract.config import ExtractionConfig

    bgr = cv2.imread(str(png_path))
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    api = PyTessBaseAPI(path=str(tessdata), lang=lang, psm=PSM.SINGLE_BLOCK)  # psm 6, como el rung 3
    try:
        api.SetImage(Image.fromarray(rgb))
        api.Recognize()
        it = api.GetIterator()
        words: list[tuple[str, float]] = []
        if it is not None:
            level = RIL.WORD
            while True:
                w = it.GetUTF8Text(level)
                c = it.Confidence(level)
                if w and w.strip():
                    words.append((w.strip(), float(c)))
                if not it.Next(level):
                    break
    finally:
        api.End()

    text = " ".join(w for w, _ in words)
    if words:
        conf = sum(len(w) * c for w, c in words) / max(1, sum(len(w) for w, _ in words))
    else:
        conf = 0.0
    coverage = field_coverage(text, ExtractionConfig().expected_fields)
    return conf, coverage, len(words)


def _coverage_of_text_layers(
    cache_root: Path, expected_fields: tuple[str, ...]
) -> list[float]:
    """Cobertura de campos sobre las capas de texto USABLES (desde el cache)."""
    out: list[float] = []
    for path in sorted(Path(cache_root).rglob("*.json")):
        name = path.name
        if "-pdf_text-" not in name:
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        feats = payload.get("features", [])
        if not feats:
            continue
        text = feats[0].get("data", "")
        if isinstance(text, str) and text:
            out.append(field_coverage(text, expected_fields))
    return out


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence", default=".sdd/metrics/evidence-dryrun.jsonl")
    ap.add_argument("--cache-root", default=".sdd/cache/dryrun")
    ap.add_argument("--tessdata", default=".sdd/tessdata")
    ap.add_argument("--lang", default="spa+eng")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--limit", type=int, default=None, help="páginas a OCR (pruebas parciales)")
    args = ap.parse_args()

    import tesserocr

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = ExtractionConfig()
    reject, _accept = _load_rung1_pages(args.evidence)

    # ---- 1. cobertura de campos en capas de texto usables del corpus
    cov_text = _coverage_of_text_layers(args.cache_root, cfg.expected_fields)

    # ---- 2. OCR real de las páginas que caerían al rung 3
    ocr_pages = []
    for row in reject:
        png = Path(args.cache_root) / "images" / f"{row['sha256']}.png"
        if not png.is_file():
            continue
        conf, cov, n_words = _ocr_page(png, Path(args.tessdata), args.lang)
        ocr_pages.append(
            {
                "invoice_id": row["invoice_id"],
                "page_sha256": row["sha256"],
                "word_conf": round(conf, 2),
                "field_coverage": round(cov, 3),
                "n_words": n_words,
                "causa_texto": row.get("detail", ""),
            }
        )
        if args.limit and len(ocr_pages) >= args.limit:
            break

    confs = [p["word_conf"] for p in ocr_pages]
    covs_ocr = [p["field_coverage"] for p in ocr_pages]

    # ---- 3. porcentajes por encima/debajo de cada umbral candidato
    def pct_above(values: list[float], threshold: float) -> float:
        if not values:
            return 0.0
        return round(100.0 * sum(1 for v in values if v >= threshold) / len(values), 1)

    candidates_conf = [40.0, 50.0, 60.0, 70.0, 80.0]
    candidates_cov = [0.2, 0.4, 0.5, 0.6, 0.8]
    table_conf = {
        str(t): {"pct_ocr_arriba": pct_above(confs, t), "pct_texto_arriba": None}
        for t in candidates_conf
    }
    table_cov = {
        str(t): {
            "pct_ocr_arriba": pct_above(covs_ocr, t),
            "pct_capas_texto_arriba": pct_above(cov_text, t),
        }
        for t in candidates_cov
    }

    measured = {
        "kind": "calibracion-rung3",
        "ocr_pages_measured": len(ocr_pages),
        "text_layers_measured": len(cov_text),
        "word_conf_ocr": {
            "mean": round(mean(confs), 1) if confs else None,
            **_percentiles(confs),
        },
        "field_coverage_ocr": {
            "mean": round(mean(covs_ocr), 3) if covs_ocr else None,
            **_percentiles(covs_ocr),
        },
        "field_coverage_capas_texto": {
            "mean": round(mean(cov_text), 3) if cov_text else None,
            **_percentiles(cov_text),
        },
        "tabla_umbral_word_conf": table_conf,
        "tabla_umbral_cobertura": table_cov,
        "ocr_pages": ocr_pages,
        "tesseract": str(tesserocr.tesseract_version()),
        "tessdata_lang": args.lang,
        "psm": 6,
    }
    (out_dir / "calibracion-rung3.json").write_text(
        json.dumps(measured, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({k: v for k, v in measured.items() if k != "ocr_pages"}, indent=2))


if __name__ == "__main__":
    main()
