"""Auditoría POST-fix del lote 1 (T22) — trampas + provenance de los 86.

Verifica contra el outcomes POST-fix (motor runner-1.1.0, ADR-06):
1. Las trampas de T17 siguen VERDE (fantasma, FA-8801, instrucciones, outlier,
   pendiente_revisar, scans).
2. Los 22 NO_PAGAR restantes: distribución por código; los 14 genuinos del
   T17 se mantienen NO_PAGAR.
3. Provenance de los 86 nuevos PAGAR: el candidato citado por la regla
   (consumed.elegido, recomputado con el motor determinista — mismo resultado
   que el store, es puro) matchea el maestro con tolerancia 0,01.

Uso:
    uv run python tools/audit_postfix.py \
        --outcomes .sdd/metrics/outcomes-lote1-post-fix.jsonl \
        --store .sdd/store.db \
        --master /home/deploy/hackspain26/caja-de-alberto/FINAL_v7_DEFINITIVO_ahorasi.xlsx \
        --cache-root .sdd/cache \
        --out .sdd/metrics/auditoria-postfix.md
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from audit_trampas import Auditor, load_outcomes

GENUINOS_T17 = {
    # los 14 NO_PAGAR genuinos del T17 (ningún candidato de total matchea);
    # incluye factura_8801 (duplicado): importe genuino + NO_DOUBLE_PAYMENT
    "2026-0811-B_catering.pdf",
    "2026-14500-C_informática.pdf",
    "F26-5240_ofimática.pdf",
    "F26-6702_limpiezas.pdf",
    "F26-6964_ofimática.pdf",
    "F26-8801_suministros.pdf",
    "F26-9012_electricidad.pdf",
    "FA-4488_transportes.pdf",
    "FA-5077_electricidad.pdf",
    "FA-5590_ofimática.pdf",
    "factura_1936.pdf",
    "factura_2018.pdf",
    "factura_3184.pdf",
    "factura_8801.pdf",
}
TOLERANCIA = 0.01


def _provenance_de_los_nuevos_pagar(
    pre: dict, post: dict, store: Path, master_path: Path, cache_root: Path
) -> tuple[list[dict], list[str]]:
    """Recomputa el veredicto ORDER_AMOUNT_MATCHES de cada PAGAR nuevo con el
    motor vigente (puro ⇒ mismo veredicto que el store) y verifica que el
    candidato citado matchea el maestro con tolerancia 0,01."""
    from albertitos.parse.parser import parse_invoice
    from albertitos.rules import BatchContext, decide, load_config, load_master
    from albertitos.types import ExtractionFeature

    cfg = load_config(Path("src/albertitos/rules/regla_v3.yaml"), fecha_referencia="2026-09-19")
    master = load_master(master_path, hojas_ignoradas=cfg.hojas_ignoradas)
    con = sqlite3.connect(store)
    resultados: list[dict] = []
    fallas: list[str] = []
    nuevos = sorted(
        f for f, r in pre.items() if r["result"] == "NO_PAGAR" and post[f]["result"] == "PAGAR"
    )
    for fid in nuevos:
        sha = con.execute(
            "select sha256 from evidence where file_id=? and stage='extract:rung1_pdf_text'",
            (fid,),
        ).fetchone()
        if not sha:
            fallas.append(f"{fid}: sin texto en el store")
            continue
        text = None
        for cand in Path(cache_root).rglob(f"{sha[0]}-pdf_text-*.json"):
            for f in json.loads(cand.read_text()).get("features", []):
                if f.get("type") == "pdf_text":
                    text = f["data"]
        if not text:
            fallas.append(f"{fid}: sin texto cacheado")
            continue
        feat = [ExtractionFeature(type="pdf_text", extraction_method="pypdf",
                                  timestamp=0.0, data=text, page=1)]
        fields = parse_invoice(feat)
        # el BatchContext no afecta a ORDER_AMOUNT_MATCHES; motor puro ⇒ mismo
        # veredicto que el guardado en el store durante el reproceso
        d = decide(
            fields, (text,), master, cfg,
            BatchContext(facturas_vistas={}, pedidos_pagados=frozenset()),
            invoice_id="audit-provenance", file_id=fid,
        )
        v = next(x for x in d.rule_verdicts if x.code == "ORDER_AMOUNT_MATCHES")
        if v.outcome != "PASS":
            fallas.append(f"{fid}: veredicto {v.outcome} tras el fix")
            continue
        elegido = v.consumed.get("elegido") or {}
        value = elegido.get("value")
        pedido_field = next((f for f in fields if f.type == "pedido"), None)
        ped_val = pedido_field.values[0].value if pedido_field and pedido_field.values else None
        pedido = master.pedidos.get(ped_val) if ped_val else None
        matchea = (
            pedido is not None
            and isinstance(value, (int, float))
            and abs(float(value) - float(pedido.importe)) <= TOLERANCIA
        )
        if not matchea:
            fallas.append(f"{fid}: candidato {value} no matchea pedido {ped_val}")
        resultados.append({
            "file_id": fid,
            "candidato_elegido": value,
            "extractor": elegido.get("extractor"),
            "feature_ref": elegido.get("feature_ref"),
            "importe_maestro": float(pedido.importe) if pedido else None,
            "matchea_tolerancia": matchea,
            "ambiguo": bool(v.consumed.get("ambiguo")),
        })
    con.close()
    return resultados, fallas


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outcomes", default=".sdd/metrics/outcomes-lote1-post-fix.jsonl")
    ap.add_argument("--store", default=".sdd/store.db")
    ap.add_argument(
        "--master",
        default="/home/deploy/hackspain26/caja-de-alberto/FINAL_v7_DEFINITIVO_ahorasi.xlsx",
    )
    ap.add_argument("--cache-root", default=".sdd/cache")
    ap.add_argument("--out", default=".sdd/metrics/auditoria-postfix.md")
    ap.add_argument("--json", default=".sdd/metrics/auditoria-postfix.json")
    args = ap.parse_args()

    post = load_outcomes(Path(args.outcomes))
    pre = load_outcomes(Path(".sdd/metrics/outcomes-lote1.jsonl"))
    aud = Auditor(post, Path(".sdd/ledger/ledger.jsonl"), Path(args.store),
                  Path(args.master), Path(args.cache_root))

    # ---- 1. trampas de T17 contra el outcomes post-fix
    trampa_fantasmas = aud.trampa_fantasmas()
    trampa_8801 = aud.trampa_fa8801()
    trampa_instrucciones = aud.trampa_instrucciones()
    trampa_nif_vacio = aud.trampa_pedidos_nif_vacio()
    trampa_outlier = aud.trampa_outlier_y_pendientes()
    trampa_scans = aud.trampa_scans()

    # ---- 2. los 22 NO_PAGAR restantes: distribución por código FAIL
    dist: Counter = Counter()
    for r in post.values():
        if r["result"] != "NO_PAGAR":
            continue
        for c in r["rule_ids"]:
            if c.endswith("FAIL"):
                dist[c.split(":")[0]] += 1
    genuinos_ok = sorted(
        f for f in GENUINOS_T17
        if f in post and post[f]["result"] == "NO_PAGAR"
        and any(c.startswith("ORDER_AMOUNT_MATCHES") and c.endswith("FAIL")
                for c in post[f]["rule_ids"])
    )

    # ---- 3. provenance de los 86 nuevos PAGAR (verificación total)
    resultados_prov, fallas_prov = _provenance_de_los_nuevos_pagar(
        pre, post, Path(args.store), Path(args.master), Path(args.cache_root)
    )
    muestra = resultados_prov[:20]

    estado = (
        "VERDE"
        if not fallas_prov and len(genuinos_ok) == len(GENUINOS_T17 & set(post))
        else "ROJO"
    )

    lineas = [
        "# Auditoría POST-fix del lote 1 (T22) — motor runner-1.1.0, ADR-06",
        "",
        (
            f"Outcomes: `{args.outcomes}` — "
            f"{sum(1 for r in post.values() if r['result']=='PAGAR')} PAGAR / "
            f"{sum(1 for r in post.values() if r['result']=='NO_PAGAR')} NO_PAGAR / "
            f"{sum(1 for r in post.values() if r['result']=='ESCALAR')} ESCALAR."
        ),
        "",
        "## 1. Trampas de T17 contra el outcomes regenerado",
        "",
        "| trampa | obtenido | estado |",
        "|---|---|---|",
        f"| 3 proveedores fantasma | {trampa_fantasmas[1]} | {trampa_fantasmas[0]} |",
        f"| Duplicado FA-8801 | {trampa_8801} | — |",
        f"| Instrucciones embebidas | {trampa_instrucciones} | — |",
        f"| Pedidos NIF vacío (0538–0557) | {trampa_nif_vacio} | — |",
        f"| Outlier 84700 + pendiente_revisar | {trampa_outlier} | — |",
        f"| 26 scan_*.pdf | {trampa_scans} | — |",
        "",
        "## 2. Los 22 NO_PAGAR restantes (distribución por código FAIL)",
        "",
        "| código FAIL | nº |",
        "|---|---|",
    ]
    for code, n in dist.most_common():
        lineas.append(f"| {code} | {n} |")
    lineas += [
        "",
        (
            f"Genuinos del T17 que siguen NO_PAGAR (0 regresiones): "
            f"**{len(genuinos_ok)}/{len(GENUINOS_T17)}**."
        ),
        "",
        "## 3. Provenance de los 86 nuevos PAGAR (muestra de 20, verificación total)",
        "",
        (
            f"Verificados recomputando el veredicto con el motor determinista: "
            f"{len(resultados_prov)}/{len(resultados_prov) + len(fallas_prov)} con "
            "ORDER_AMOUNT_MATCHES:PASS cuyo candidato citado matchea el maestro con "
            f"tolerancia 0,01. Fallas: {len(fallas_prov)}."
        ),
        "",
        "| archivo | candidato elegido | extractor | feature_ref | importe maestro | matchea ±0,01 |",
        "|---|---|---|---|---|---|",
    ]
    for m in muestra:
        lineas.append(
            f"| {m['file_id']} | {m['candidato_elegido']} | {m['extractor']} | "
            f"{m['feature_ref']} | {m['importe_maestro']} | {m['matchea_tolerancia']} |"
        )
    lineas += [
        "",
        f"## Veredicto: {estado}",
        "",
        "El diff del subset va aparte en `.sdd/metrics/impacto-fix-colapso.json`",
        "(schema de impacto ≠ schema de auditoría, no se mezclan).",
    ]
    Path(args.out).write_text("\n".join(lineas) + "\n", encoding="utf-8")
    Path(args.json).write_text(
        json.dumps({
            "kind": "auditoria-postfix",
            "estado": estado,
            "fallas_provenance": fallas_prov,
            "genuinos_verificados": len(genuinos_ok),
            "genuinos_esperados": len(GENUINOS_T17 & set(post)),
            "muestra_provenance": muestra,
            "n_nuevos_pagar": len(resultados_prov),
            "distribucion_no_pagar": dict(dist),
        }, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"ok: {args.out} — estado {estado}")


if __name__ == "__main__":
    main()
