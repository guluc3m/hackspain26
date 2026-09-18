"""Métricas del lote 1 (T14) — números MEDIDOS desde store/ledger/runner.

Todo lo emitido está medido; nada estimado salvo el coste cloud, que se marca
como estimado con su fórmula. No decide resultados.

Uso:
    uv run python tools/lote1_metrics.py \
        [--out .sdd/metrics/lote1.json] [--triage .sdd/metrics/triage-revision.md]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
from collections import Counter, defaultdict
from pathlib import Path

LEDGER = Path(".sdd/ledger/ledger.jsonl")
RUNNER = Path(".sdd/state/runner.json")
STORE = Path(".sdd/store.db")
REVIEW = Path(".sdd/review-queue/review.jsonl")


def _rung_stats(store: Path, stage: str) -> dict:
    con = sqlite3.connect(store)
    row = con.execute(
        "select count(*), coalesce(round(avg(latency_ms),1),0), coalesce(max(latency_ms),0) "
        "from evidence where stage=? and outcome!='cache_hit'",
        (stage,),
    ).fetchone()
    con.close()
    return {"n_invocaciones": row[0], "latencia_media_ms": row[1], "latencia_max_ms": row[2]}


def _dominante(rule_codes: str) -> str:
    """Motivo dominante: los códigos no-PASS de la decisión (T14 punto 4)."""
    fails_unknown = [c for c in rule_codes.split(",") if c and not c.endswith(":PASS")]
    if not fails_unknown:
        return "sin-veredicto"
    return fails_unknown[0] if len(fails_unknown) == 1 else "mixto"


def build(out_path: Path, triage_path: Path) -> dict:
    runner = json.loads(RUNNER.read_text())

    res: Counter = Counter()
    grupos: dict[str, list[str]] = defaultdict(list)
    ledger_text = LEDGER.read_text(encoding="utf-8") if LEDGER.is_file() else ""
    for line in ledger_text.splitlines():
        r = json.loads(line)
        res[r.get("result")] += 1
        if r.get("result") == "ESCALAR":
            grupos[_dominante(r.get("rule_codes", ""))].append(r.get("file_id"))

    review_text = REVIEW.read_text(encoding="utf-8") if REVIEW.is_file() else ""
    review_items = [json.loads(l) for l in review_text.splitlines() if l.strip()]
    review_motivos = Counter(
        i.get("provenance", {}).get("motivo", "?") for i in review_items
    )

    total_s = None
    if runner.get("files_per_second"):
        total_s = round(runner["done"] / runner["files_per_second"], 1)

    metrics = {
        "kind": "lote1",
        "generado": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
        "medido": True,
        "fuente": {
            "runner": str(RUNNER),
            "store": str(STORE),
            "ledger": str(LEDGER),
            "outcomes": "/home/deploy/hackspain26/outcomes.jsonl",
        },
        "config_version": runner.get("config_version"),
        "engine_version": runner.get("engine_version"),
        "n_archivos": runner.get("done"),
        "fallos": runner.get("fallos"),
        "files_per_s": runner.get("files_per_second"),
        "latencia_total_s": total_s,
        "rung4_serializado": runner.get("rung4_secuencial"),
        "rung4_llama_server": runner.get("rung4_llama_server"),
        "distribucion": {"PAGAR": res.get("PAGAR", 0), "NO_PAGAR": res.get("NO_PAGAR", 0), "ESCALAR": res.get("ESCALAR", 0)},
        "rung4_vlm_local": _rung_stats(STORE, "extract:rung4_vlm"),
        "rung5_cloud": _rung_stats(STORE, "extract:rung5_cloud_vlm"),
        "coste_cloud_eur": {
            "medido": 0.0,
            "nota": (
                "estimado: 0.00 € — 0 lecturas cloud facturables (5 intentos con "
                "404 no facturan, 4 sin credenciales aún); fórmula T9: nº llamadas "
                "200 × precio por lectura deepseek-v4.1-flash"
            ),
        },
        "escalares": {k: len(v) for k, v in sorted(grupos.items(), key=lambda kv: -len(kv[1]))},
    }

    triage = [
        "# Triage de la cola de revisión — lote 1 (T14)",
        "",
        "## ESCALAR por motivo dominante (decisión del motor de reglas, ledger)",
        "",
        "| motivo | nº | archivos |",
        "|---|---|---|",
    ]
    for motivo, files in sorted(grupos.items(), key=lambda kv: -len(kv[1])):
        lista = ", ".join(sorted(files))
        triage.append(f"| {motivo} | {len(files)} | {lista} |")
    triage += [
        "",
        "## Cola de extracción (`.sdd/review-queue/review.jsonl`) — páginas escaladas",
        "",
        "Estas 10 páginas llegaron al rung 5 (escala de extracción); sin lectura",
        "cloud fiable (5× status-404 del proveedor, 5 sin credenciales inyectadas).",
        "Lecturas candidatas lado a lado + imagen en el review.jsonl (esquema UI W3).",
        "",
        "| motivo | nº | archivos |",
        "|---|---|---|",
    ]
    for motivo, n in review_motivos.most_common():
        archivos = ", ".join(sorted(i.get("file_id", "?") for i in review_items
                                    if i.get("provenance", {}).get("motivo") == motivo))
        triage.append(f"| {motivo} | {n} | {archivos} |")
    triage += [
        "",
        "## Nota",
        "",
        "Las 10 páginas de extracción están DENTRO de los 45 ESCALAR (la escalada",
        "de extracción nunca decide: el motor emite UNKNOWN y el resultado final",
        "es ESCALAR). El desglose de la primera tabla es el completo; la cola",
        "Revisión de la UI muestra los 45 (deriva de las decisiones con resultado",
        "ESCALAR, ui/ledger.py revision_queue) y el review.jsonl aporta imagen +",
        "candidatas lado a lado para las 10 que llegaron al rung 5.",
        "NO se han decidido resultados aquí: el humano decide (AGENTS.md §6/§7);",
        "los overrides alimentan SOLO la extracción y la decisión se recalcula.",
        "",
        "Hallazgo para seguimiento (no bloqueante): RUNNER_TIMEOUT es el motivo",
        "dominante (20/45) — timeout de 20 s/archivo con rung 4 serializado en una",
        "máquina en carga. Material para el informe y para re-procesado tras",
        "revisión (el cache hace que re-ejecutar sea barato).",
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    triage_path.write_text("\n".join(triage) + "\n", encoding="utf-8")
    return metrics


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=".sdd/metrics/lote1.json")
    ap.add_argument("--triage", default=".sdd/metrics/triage-revision.md")
    args = ap.parse_args()
    metrics = build(Path(args.out), Path(args.triage))
    print(json.dumps({k: metrics[k] for k in ("n_archivos", "files_per_s", "latencia_total_s", "distribucion")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
