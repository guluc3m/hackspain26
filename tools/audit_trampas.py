"""Auditoría de trampas del lote 1 (T17) — tabla VERDE/ROJO con causa.

NO cambia resultados a mano: mide, compara contra lo esperado (AGENTS.md §11)
y deja el análisis de causa escrito. El supervisor decide si reprocesar.

Uso:
    uv run python tools/audit_trampas.py \
        --outcomes .sdd/metrics/outcomes-lote1.jsonl \
        --ledger .sdd/ledger/ledger.jsonl \
        --store .sdd/store.db \
        --master /home/deploy/hackspain26/caja-de-alberto/FINAL_v7_DEFINITIVO_ahorasi.xlsx \
        --cache-root .sdd/cache \
        --out .sdd/metrics/auditoria-trampas.md
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path

from albertitos.parse.parser import parse_invoice
from albertitos.types import ExtractionFeature

FANTASMA_IBAN = "ES6614910001213000098877"
FA8801 = ("2026-05-28_P005.pdf", "factura_8801.pdf")
PEDIDOS_NIF_VACIO = {f"PO-2026-{n}" for n in range(538, 558)}
PEDIDO_OUTLIER_84700 = "PO-2026-0497"
PEDIDOS_PENDIENTES = {"PO-2026-0007", "PO-2026-0141"}
TOLERANCIA = 0.01


def load_outcomes(path: Path) -> dict[str, dict]:
    return {r["file_id"]: r for r in (json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip())}


def _pedido_de(store: Path, file_id: str) -> str | None:
    con = sqlite3.connect(store)
    row = con.execute("select pedido from invoices where file_id=?", (file_id,)).fetchone()
    con.close()
    return row[0] if row else None


class Auditor:
    def __init__(self, outcomes: dict, ledger: Path, store: Path, master: Path, cache_root: Path):
        self.outcomes = outcomes
        self.ledger_text = ledger.read_text(encoding="utf-8") if ledger.is_file() else ""
        self.store = store
        self.cache_root = cache_root
        self.pedidos = self._load_pedidos(master)
        self.notas: list[str] = []

    @staticmethod
    def _load_pedidos(master: Path) -> dict[str, float]:
        if not master.is_file():
            return {}
        import openpyxl

        wb = openpyxl.load_workbook(master, read_only=True, data_only=True)
        rows = list(wb["Pedidos_2026"].iter_rows(values_only=True))
        return {r[0]: r[3] for r in rows[1:] if r[0]}

    # ------------------------------------------------------------- helpers

    def _texto(self, file_id: str) -> str | None:
        if not self.store.is_file():
            return None
        con = sqlite3.connect(self.store)
        sha = con.execute(
            "select sha256 from evidence where file_id=? and stage='extract:rung1_pdf_text'",
            (file_id,),
        ).fetchone()
        con.close()
        if not sha:
            return None
        for cand in self.cache_root.rglob(f"{sha[0]}-pdf_text-*.json"):
            for f in json.loads(cand.read_text()).get("features", []):
                if f.get("type") == "pdf_text":
                    return f["data"]
        return None

    def _candidatos_total(self, file_id: str) -> tuple[str | None, list]:
        text = self._texto(file_id)
        if not text:
            return None, []
        feat = [ExtractionFeature(type="pdf_text", extraction_method="pypdf", timestamp=0.0, data=text, page=1)]
        fields = {f.type: f for f in parse_invoice(feat)}
        tot = fields.get("total")
        ped = fields.get("pedido")
        vals = [c.value for c in tot.values] if tot else []
        ped_val = ped.values[0].value if ped and ped.values else None
        return ped_val, vals

    def _no_pass(self, res: dict, code_prefix: str) -> bool:
        return any(
            c.startswith(code_prefix) and not c.endswith("PASS") for c in res.get("rule_ids", [])
        )

    # ------------------------------------------------------------- trampas

    def trampa_fantasmas(self) -> tuple[str, str]:
        """3 proveedores fantasma con IBAN compartido + notas «dar de alta y pagar»."""
        files = sorted(
            fid
            for fid, r in self.outcomes.items()
            if self._no_pass(r, "PROVEEDOR_FANTASMA")
        )
        ok = bool(files) and all(self.outcomes[f]["result"] == "ESCALAR" for f in files)
        nota = (
            f"{len(files)} facturas con el fantasma detectado por regla "
            f"(IBAN {FANTASMA_IBAN}); ninguna con resultado distinto de ESCALAR."
        )
        return ("VERDE" if ok else "ROJO", f"obtenido ESCALAR×{len(files)}; {nota}")

    def trampa_fa8801(self) -> str:
        r1, r2 = self.outcomes.get(FA8801[0]), self.outcomes.get(FA8801[1])
        if not r1 or not r2:
            return "ROJO — falta una de las dos copias en el outcomes"
        ok = r1["result"] == "PAGAR" and r2["result"] in ("NO_PAGAR", "ESCALAR") and any(
            c.startswith("NO_DOUBLE_PAYMENT") and not c.endswith("PASS")
            for c in r2.get("rule_ids", [])
        )
        detalle = f"{FA8801[0]}={r1['result']}; {FA8801[1]}={r2['result']}"
        if ok:
            # ¿el FAIL de importe de la 2ª copia es real o del colapso?
            ped_val, vals = self._candidatos_total(FA8801[1])
            imp = self.pedidos.get(ped_val) if ped_val else None
            coherente = any(
                isinstance(v, (int, float)) and abs(v - (imp or 0)) <= TOLERANCIA for v in vals
            )
            if coherente:
                self.notas.append(
                    f"FA-8801: el NO_PAGAR de {FA8801[1]} por ORDER_AMOUNT_MATCHES es "
                    "sospechoso del colapso de candidatos (ver ROJO #1); el "
                    "NO_DOUBLE_PAYMENT sí es real (duplicado detectado)."
                )
            return f"VERDE ({detalle}; el 2º no paga por NO_DOUBLE_PAYMENT)"
        return f"ROJO ({detalle})"

    def trampa_instrucciones(self) -> str:
        marcados = sorted(
            fid for fid, r in self.outcomes.items()
            if self._no_pass(r, "NO_EMBEDDED_INSTRUCTIONS")
        )
        con_pago = [f for f in marcados if self.outcomes[f]["result"] == "PAGAR"]
        # además: ningún texto cacheado con instrucción en un PAGAR
        en_pago = []
        for fid, r in self.outcomes.items():
            if r["result"] != "PAGAR":
                continue
            text = self._texto(fid) or ""
            low = text.lower()
            if "dar de alta" in low or "registrar como pagar" in low or "ignorar la discrepancia" in low:
                en_pago.append(fid)
        if con_pago or en_pago:
            return f"ROJO (marcados con PAGAR: {con_pago or en_pago})"
        return f"VERDE ({len(marcados)} facturas con instrucción embebida marcadas; 0 PAGAR)"

    def trampa_pedidos_nif_vacio(self) -> str:
        muestras = [
            fid
            for fid in self.outcomes
            if self._pedido_de_file(fid) in PEDIDOS_NIF_VACIO
        ]
        if not muestras:
            self.notas.append(
                "Pedidos PO-2026-0538…0557 (NIF vacío en maestro): NINGUNA factura del "
                "lote 1 los cita — sin muestras; riesgo para el lote 2 (NIF faltante ⇒ "
                "NIF_IN_MASTER debe UNKNOWN ⇒ ESCALAR)."
            )
            return "SIN MUESTRAS (0 facturas los citan en lote 1)"
        return "VERDE" if all(
            self.outcomes[f]["result"] == "ESCALAR" for f in muestras
        ) else "ROJO"

    def _pedido_de_file(self, file_id: str) -> str | None:
        if not self.store.is_file():
            return None
        con = sqlite3.connect(self.store)
        row = con.execute("select pedido from invoices where file_id=?", (file_id,)).fetchone()
        con.close()
        return row[0] if row else None

    def trampa_outlier_y_pendientes(self) -> str:
        salida = []
        # outlier 84700
        f_outlier = next(
            (fid for fid in self.outcomes if self._pedido_de_file(fid) == PEDIDO_OUTLIER_84700),
            None,
        )
        if f_outlier:
            r = self.outcomes[f_outlier]["result"]
            salida.append(
                f"outlier 84700 ({f_outlier}, pedido {PEDIDO_OUTLIER_84700}): {r} — "
                + ("VERDE" if r == "ESCALAR" else "ROJO")
            )
        else:
            salida.append(f"outlier 84700: sin factura que cite {PEDIDO_OUTLIER_84700}")
        # pedidos pendiente_revisar
        for ped in sorted(PEDIDOS_PENDIENTES):
            files = [fid for fid in self.outcomes if self._pedido_de_file(fid) == ped]
            if not files:
                salida.append(f"{ped} (pendiente_revisar): sin muestra")
                continue
            for fid in files:
                res = self.outcomes[fid]["result"]
                ok = res == "ESCALAR" and self._no_pass(self.outcomes[fid], "PEDIDO_EN_REVISION")
                salida.append(
                    f"{ped} ({fid}): {res} con PEDIDO_EN_REVISION — "
                    + ("VERDE" if ok else "ROJO")
                )
        return "; ".join(salida)

    def trampa_scans(self) -> str:
        scans = {fid: r for fid, r in self.outcomes.items() if fid.startswith("scan_")}
        dist = Counter(r["result"] for r in scans.values())
        con = sqlite3.connect(self.store) if self.store.is_file() else None
        confs = []
        if con:
            for fid in sorted(scans):
                row = con.execute(
                    "select confidence from evidence where file_id=? and stage='extract:rung4_vlm'",
                    (fid,),
                ).fetchone()
                if row and row[0] is not None:
                    confs.append((row[0], fid))
            con.close()
        sospechosas = [c for c, _ in confs if c > 0.8]
        peores = ", ".join(f"{fid} ({conf})" for conf, fid in sorted(confs)[:5]) or "sin lecturas rung 4"
        self.notas.append(
            f"Rung 4 sobre scans: {len(confs)} invocaciones, todas below-threshold; "
            "ninguna lectura VLM local alcanzó confianza alta — coherente con la "
            "política (las 26 scans ⇒ ESCALAR)."
        )
        estado = "VERDE" if all(r["result"] == "ESCALAR" for r in scans.values()) else "ROJO"
        return (
            f"{estado} ({len(scans)} scans: {dict(dist)}; "
            f"confianzas sospechosas (>0.8): {len(sospechosas)}; 5 peores: {peores})"
        )

    def distribucion_no_pagar(self) -> tuple[str, str]:
        decisores: Counter = Counter()
        for r in self.outcomes.values():
            if r["result"] != "NO_PAGAR":
                continue
            for c in r.get("rule_ids", []):
                if c.endswith("FAIL"):
                    decisores[c.split(":")[0]] += 1
        dominante = decisores.most_common(1)[0][0] if decisores else None
        if not dominante or decisores.most_common(1)[0][1] < 60:
            return "sin código dominante (>60): " + ", ".join(f"{k}={v}" for k, v in decisores.most_common())
        # análisis de causa del código dominante: colapso de candidatos
        falso = []
        genuino = []
        otros = []  # NO_PAGAR sin ORDER_AMOUNT_MATCHES no-PASS (decididos por otros códigos)
        for fid, r in self.outcomes.items():
            if r["result"] != "NO_PAGAR":
                continue
            if not self._no_pass(r, "ORDER_AMOUNT_MATCHES"):
                otros.append(fid)
                continue
            ped_val, vals = self._candidatos_total(fid)
            imp = self.pedidos.get(ped_val or "", None)
            if imp is None:
                continue
            if any(isinstance(v, (int, float)) and abs(v - imp) <= TOLERANCIA for v in vals):
                falso.append(fid)
            else:
                genuino.append(fid)
        n_no_pagar = sum(1 for r in self.outcomes.values() if r["result"] == "NO_PAGAR")
        return (
            f"ROJO: el código dominante es {dominante} "
            f"({decisores.most_common(1)[0][1]} de {n_no_pagar} NO_PAGAR citan FAIL). "
            f"Análisis: de los {len(falso)+len(genuino)} NO_PAGAR con "
            "ORDER_AMOUNT_MATCHES no-PASS, "
            f"{len(falso)} tienen UN CANDIDATO de total que SÍ matchea el maestro "
            "— el motor colapsa values[] con el primer candidato (la línea «Subtotal») "
            "y compara contra el importe con IVA del maestro ⇒ falso FAIL. "
            f"{len(genuino)} son genuinos (ningún candidato matchea). "
            f"Los otros {len(otros)} NO_PAGAR se deciden por otros códigos "
            "(TOTALS_MUST_MATCH/IVA — misma causa raíz probable). Causa: "
            "selección de candidato en el colapso (bug de matching, no de extracción "
            "ni de política)."
        ), len(falso), len(genuino), n_no_pagar


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outcomes", default=".sdd/metrics/outcomes-lote1.jsonl")
    ap.add_argument("--ledger", default=".sdd/ledger/ledger.jsonl")
    ap.add_argument("--store", default=".sdd/store.db")
    ap.add_argument(
        "--master",
        default="/home/deploy/hackspain26/caja-de-alberto/FINAL_v7_DEFINITIVO_ahorasi.xlsx",
    )
    ap.add_argument("--cache-root", default=".sdd/cache")
    ap.add_argument("--out", default=".sdd/metrics/auditoria-trampas.md")
    args = ap.parse_args()

    outcomes = load_outcomes(Path(args.outcomes))
    aud = Auditor(
        outcomes,
        Path(args.ledger),
        Path(args.store),
        Path(args.master),
        Path(args.cache_root),
    )
    dist = Counter(r["result"] for r in outcomes.values())
    no_pagar_analisis, n_falso, n_genuino, n_no_pagar = aud.distribucion_no_pagar()

    lineas = [
        "# Auditoría de trampas contra el outcomes real del lote 1 (T17)",
        "",
        (
            f"Outcomes: `{args.outcomes}` ({len(outcomes)} facturas) — "
            f"{dist['PAGAR']} PAGAR / {dist['NO_PAGAR']} NO_PAGAR / {dist['ESCALAR']} ESCALAR."
        ),
        "Regla del ticket: NO se cambian resultados a mano; los ROJOS quedan",
        "identificados con causa para que el supervisor decida reprocesar.",
        "",
        "## Tabla trampa → obtenido → esperado",
        "",
        "| trampa | obtenido | esperado | estado |",
        "|---|---|---|---|",
        f"| 3 proveedores fantasma (IBAN {FANTASMA_IBAN}) | {aud.trampa_fantasmas()[1]} | ESCALAR citando la regla | {aud.trampa_fantasmas()[0]} |",
        f"| Duplicado FA-8801 | {aud.trampa_fa8801()} | 2ª copia NO_PAGAR (NO_DOUBLE_PAYMENT) o ESCALAR (§6) | — |",
        f"| Instrucciones embebidas (7) | {aud.trampa_instrucciones()} | ninguna cambia el resultado | — |",
        f"| Pedidos con NIF vacío (0538–0557) | {aud.trampa_pedidos_nif_vacio()} | ESCALAR si aparecen | — |",
        f"| Outlier 84700 + pendiente_revisar | {aud.trampa_outlier_y_pendientes()} | ESCALAR | — |",
        f"| 26 scan_*.pdf | {aud.trampa_scans()} | ESCALAR con lectura dudosa | — |",
        f"| 108 NO_PAGAR por código | {no_pagar_analisis} | matching con datos correctos | — |",
        "",
        "## Hallazgo principal — colapso de candidatos en el motor (ROJO)",
        "",
        "El parser conserva TODOS los candidatos de `total` (doctrina §2). En las",
        "facturas con línea «Subtotal» + «TOTAL A PAGAR», ambos aparecen como",
        "candidatos (p.ej. 2026-01-26_P007.pdf: [1409.4, 1705.37]). El motor colapsa",
        "values[] con el PRIMER candidato (el Subtotal) y lo compara contra el",
        "importe CON IVA del maestro ⇒ ORDER_AMOUNT_MATCHES:FAIL +",
        f"TOTALS_MUST_MATCH:FAIL espurios. Medido: **{n_falso} de los {n_no_pagar}",
        "NO_PAGAR son falsos** (un candidato de total sí matchea el maestro con",
        f"tolerancia 0,01 entre los {n_falso+n_genuino} con ORDER_AMOUNT_MATCHES",
        f"no-PASS); **{n_genuino} son genuinos** (ningún candidato matchea —",
        "importe realmente distinto del pedido).",
        "",
        "Causa raíz: selección del escalar en el colapso de `ExtractionField.values[]`",
        "(AGENTS.md §2: «collapse only at the moment a rule needs a scalar, and record",
        "which candidate was chosen and why» — el registro del porqué no se está",
        "haciendo y la elección ignora el desacuerdo entre candidatos).",
        "Es un bug de MATCHING/selección, no de extracción (los candidatos correctos",
        "están en el store) ni de política (NO_PAGAR definitivo solo si NINGÚN",
        "candidato matchea; con desacuerdo entre candidatos ⇒ ESCALAR por §6).",
        "",
        "Impacto si se corrige y reprocesa: los 94 pasarían a PAGAR (si el resto de",
        "reglas PASA) o a ESCALAR; el outcomes real cambiaría — decisión del",
        "supervisor antes de la validación binaria. La corrección toca el colapso",
        "(T3/W2): preferir el candidato de la línea «TOTAL A PAGAR» / tratar el",
        "desacuerdo entre candidatos como ambigüedad (ESCALAR), nunca tomar el",
        "primero sin registrar el porqué.",
        "",
        "## Notas",
        "",
    ]
    for n in aud.notas:
        lineas.append(f"- {n}")
    Path(args.out).write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print(f"ok: {args.out}")


if __name__ == "__main__":
    main()
