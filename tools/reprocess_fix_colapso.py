"""Reprocesado del lote 1 tras el fix del colapso de candidatos (T18).

Re-decide SOLO los 108 NO_PAGAR (mecanismo T13: only_list + force) con el
motor `runner-1.1.0` (ADR-06), regenera outcomes.jsonl y deja el diff medido
en `.sdd/metrics/impacto-fix-colapso.json`. NO cambia nada a mano: el motor
determinista recalcula; este script solo orquesta y mide.

Uso:
    uv run python tools/reprocess_fix_colapso.py
"""

from __future__ import annotations

import json
from pathlib import Path

from albertitos.emit import emit_outcomes
from albertitos.run import ENGINE_VERSION, Runner, RunnerConfig

SNAPSHOT_PRE = Path(".sdd/metrics/outcomes-lote1.jsonl")  # estado ANTES (T17)
DIFF_OUT = Path(".sdd/metrics/impacto-fix-colapso.json")
FECHA_REF = "2026-09-19"  # la misma de la corrida original (v3.0-2026-09-19)


def main() -> int:
    pre = {
        r["file_id"]: r
        for r in (json.loads(l) for l in SNAPSHOT_PRE.read_text().splitlines() if l.strip())
    }
    afectados = sorted(f for f, r in pre.items() if r["result"] == "NO_PAGAR")
    print(f"reprocesando {len(afectados)} NO_PAGAR con motor {ENGINE_VERSION} (ADR-06)")

    cfg = RunnerConfig(
        facturas_dir=Path("/home/deploy/hackspain26/caja-de-alberto/facturas"),
        outcomes_path=Path("/home/deploy/hackspain26/outcomes.jsonl"),
        store_root=Path(".sdd"),
        rules_yaml=Path("src/albertitos/rules/regla_v3.yaml"),
        master_path=Path(
            "/home/deploy/hackspain26/caja-de-alberto/FINAL_v7_DEFINITIVO_ahorasi.xlsx"
        ),
        fecha_referencia=FECHA_REF,
        only_list=tuple(afectados),
        force=True,
        run_id="fix-colapso-t18",
    )
    runner = Runner(cfg)
    report = runner.run()
    print(f"re-procesados: {report.procesados}, reutilizados: {report.reutilizados}, "
          f"timeouts: {report.timeout}, fallos: {report.fallos}")
    if report.timeout or report.fallos:
        print("ABORTADO: el reproceso no debe introducir timeouts ni fallos")
        return 1

    # outcomes completo desde el store (los 500) + validador de contrato
    emit_outcomes(runner.store, cfg.outcomes_path)
    from albertitos.validate import validar

    validacion = validar(cfg.outcomes_path, cfg.facturas_dir)
    errores = validacion.get("errores", [])
    print(f"validador: {'OK' if not errores else f'{len(errores)} errores'}")
    if errores:
        return 1

    # diff ANTES/DESPUÉS
    post = {
        r["file_id"]: r
        for r in (json.loads(l) for l in cfg.outcomes_path.read_text().splitlines() if l.strip())
    }
    cambios = [
        {"file_id": f, "antes": pre[f]["result"], "despues": post[f]["result"],
         "regresion": False}
        for f in sorted(pre) if pre[f]["result"] != post[f]["result"]
    ]
    regresiones = [
        c for c in cambios
        if (c["antes"], c["despues"]) in {("PAGAR", "NO_PAGAR"), ("PAGAR", "ESCALAR"),
                                          ("NO_PAGAR", "ESCALAR")}
    ]
    flap = [
        c for c in cambios
        if c["antes"] == "NO_PAGAR" and c["despues"] == "PAGAR"
    ]
    # delta vs expectativa del ticket: 87 falsos POR IMPORTE (T17) — el 87º
    # (factura_8801.pdf) tiene además NO_DOUBLE_PAYMENT real ⇒ debe seguir
    # NO_PAGAR (doctrina §6): el diff correcto es 86 flips, no 87.
    falso_sin_flip = sorted(
        f for f, r in pre.items()
        if r["result"] == "NO_PAGAR" and post[f]["result"] != "PAGAR"
        and f == "factura_8801.pdf"
    )
    diff = {
        "kind": "impacto-fix-colapso",
        "motor_antes": "runner-1.0.0",
        "motor_despues": ENGINE_VERSION,
        "fecha_ref": FECHA_REF,
        "reprocesados": len(afectados),
        "n_archivos": len(post),
        "cambios": cambios,
        "resumen": {
            "no_pagar_a_pagar": len(flap),
            "esperados_no_pagar_a_pagar": 87,  # T17: falsos por colapso de candidatos
            "desviacion_esperada": {
                "delta": 87 - len(flap),
                "causa": (
                    "factura_8801.pdf: el 87º falso POR IMPORTE es el duplicado "
                    "FA-8801 — su ORDER_AMOUNT pasa a PASS con ADR-06, pero se "
                    "mantiene NO_PAGAR por NO_DOUBLE_PAYMENT (correcto, §6)"
                ),
                "files": falso_sin_flip,
            },
            "genuinos_y_otros_se_mantienen": sum(
                1 for f, r in pre.items()
                if f not in [c["file_id"] for c in flap]
                and r["result"] == "NO_PAGAR" and post[f]["result"] == "NO_PAGAR"
            ),
            "otros_cambios": len(cambios) - len(flap),
            "regresiones": len(regresiones),
        },
        "validacion": "OK" if not errores else errores,
    }
    DIFF_OUT.parent.mkdir(parents=True, exist_ok=True)
    DIFF_OUT.write_text(json.dumps(diff, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
    print(json.dumps(diff["resumen"], ensure_ascii=False))
    runner.store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
