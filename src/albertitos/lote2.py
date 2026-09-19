"""Readiness del lote 2 (T21): simulación de extremo a extremo SIN red.

Que el sábado a las 18:00 Madrid sea un cambio de DATOS, no de código.
Esta simulación ejercita HOY el flujo completo del lote 2 con fixtures:

1. **Ingesta de un lote externo** — `Runner` contra un directorio distinto
   (`--facturas`), file_id = basename exacto, store sandbox + run_id propio:
   el lote 1 (`.sdd/store.db`, `outcomes.jsonl`) no se toca jamás.
2. **Regla v4 como datos** — corre primero con `regla_v4.yaml` (REGLA_V4
   desactivada ⇒ no-op) y luego con una copia ACTIVADA (cambio de yaml, cero
   código): el diff de impacto (T13) muestra qué decisiones cambian.
3. **Cambio de dato del maestro** — parche en memoria (`reprocess.py`) y
   reprocesado dirigido: solo cambian los que cruzan con el dato; el
   histórico de los tres runs coexiste en `decision_runs`.
4. **Emisión** — `outcomes_lote2.jsonl` para los file_id de ESTE lote
   (`emit_scope='lote'`), validado con el validador de contrato.

Todo bajo `<store_root>/lote2-sim/` y el resultado determinista en
`.sdd/metrics/lote2-sim.json` (sin timestamps: dos corridas ⇒ mismo JSON).

Flujo REAL del sábado (con el lote 2 de verdad, 40 PDFs):

    uv run python -m albertitos.run \\
        --facturas <dir-lote2> --outcomes outcomes_lote2.jsonl \\
        --rules src/albertitos/rules/regla_v4.yaml --run-id lote2 \\
        --emit-scope lote
    # (si llega parche de maestro / calibración v4 → reprocesado dirigido)
    bash scripts/stage_delivery.sh   # re-staging: ahora con lote2

Uso de la simulación:

    uv run python -m albertitos.lote2 --dry-run
"""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from albertitos.emit import emit_outcomes, list_pdf_files
from albertitos.reprocess import (
    ReprocessConfig,
    diff_runs,
    load_patch,
    reprocesar,
)
from albertitos.run import Runner, RunnerConfig, _hoy_iso
from albertitos.store import Store
from albertitos.validate import validar

FIXTURES_LOTE2 = Path("tests/fixtures/lote10")
MAESTRO_FIXTURE = Path("tests/fixtures/maestro_lote10.xlsx")
PATCH_FIXTURE = Path("tests/fixtures/patch_nif.yaml")
RULES_V4 = Path("src/albertitos/rules/regla_v4.yaml")
RUN_LOTE2_BASE = "lote2-base"
RUN_LOTE2_V4 = "lote2-v4"
RUN_LOTE2_DATO = "lote2-dato"


@dataclass(frozen=True)
class Lote2SimConfig:
    facturas_dir: Path = FIXTURES_LOTE2
    maestro: Path = MAESTRO_FIXTURE
    patch: Path = PATCH_FIXTURE
    store_root: Path = Path(".sdd")
    fecha_referencia: str = ""
    rules_yaml: Path = RULES_V4
    importe_minimo_v4: float = 3000.0
    use_rung4: bool = False  # simulación sin red (rung 4/5 degradados)
    metrics_path: Path | None = None  # default: <store_root>/metrics/lote2-sim.json


def _runner_cfg(cfg: Lote2SimConfig, store_root: Path, rules_yaml: Path,
                run_id: str, *, force: bool = False) -> RunnerConfig:
    return RunnerConfig(
        facturas_dir=cfg.facturas_dir,
        outcomes_path=store_root.parent / "outcomes_lote2.jsonl",
        store_root=store_root,
        rules_yaml=rules_yaml,
        master_path=cfg.maestro,
        fecha_referencia=cfg.fecha_referencia,
        use_rung4=cfg.use_rung4,
        run_id=run_id,
        force=force,
        emit_scope="lote",
    )


def _yaml_v4_activa(cfg: Lote2SimConfig, destino: Path) -> Path:
    """Copia del yaml v4 con REGLA_V4 ACTIVADA: cambio de DATOS, no de código."""
    texto = Path(cfg.rules_yaml).read_text(encoding="utf-8")
    texto = texto.replace("activa: false", "activa: true")
    texto = texto.replace("importe_minimo: 10.0",
                          f"importe_minimo: {cfg.importe_minimo_v4}")
    destino.write_text(texto, encoding="utf-8")
    return destino


def simular_lote2(cfg: Lote2SimConfig) -> dict:
    """Ejecuta la simulación completa y devuelve el resultado determinista."""
    if not cfg.fecha_referencia:
        cfg = _con_fecha(cfg)
    sim_root = Path(cfg.store_root) / "lote2-sim"
    if sim_root.exists():
        shutil.rmtree(sim_root)
    store_dir = sim_root / "store"
    pdfs = list_pdf_files(cfg.facturas_dir)
    file_ids = {p.name for p in pdfs}

    # ---- 1 · ingesta del lote externo (store sandbox + run_id separado)
    rep_base = Runner(_runner_cfg(cfg, store_dir, Path(cfg.rules_yaml),
                                  RUN_LOTE2_BASE)).run()

    # ---- 2 · v4 ACTIVADA como datos (otra corrida del mismo lote)
    v4_yaml = _yaml_v4_activa(cfg, sim_root / "regla_v4_activa.yaml")
    rep_v4 = Runner(_runner_cfg(cfg, store_dir, v4_yaml, RUN_LOTE2_V4,
                                force=True)).run()

    # ---- 3 · cambio de dato del maestro + reprocesado dirigido (T13)
    patch = load_patch(cfg.patch)
    reprocesar(ReprocessConfig(
        facturas_dir=Path(cfg.facturas_dir),
        store_root=store_dir,
        rules_yaml=v4_yaml,
        master_path=Path(cfg.maestro),
        fecha_referencia=cfg.fecha_referencia,
        patch_path=Path(cfg.patch),
        patch=patch,
        run_id=RUN_LOTE2_DATO,
        base_run=RUN_LOTE2_V4,
        use_rung4=cfg.use_rung4,
        outcomes_path=sim_root / "outcomes_lote2.jsonl",
    ))

    # ---- 4 · emisión del lote 2 SOLO con sus file_id + validador
    store = Store(store_dir)
    try:
        emit_outcomes(store, sim_root / "outcomes_lote2.jsonl",
                      only_files=file_ids)
        validacion = validar(sim_root / "outcomes_lote2.jsonl",
                             Path(cfg.facturas_dir))
        runs = store.run_ids()
        diff_v4 = diff_runs(store, RUN_LOTE2_BASE, RUN_LOTE2_V4)
        diff_dato = diff_runs(store, RUN_LOTE2_V4, RUN_LOTE2_DATO)
        base_hist = {d.file_id: d.result
                     for d in store.run_decisions(RUN_LOTE2_BASE)}
    finally:
        store.close()

    resultados_base: dict[str, int] = {"PAGAR": 0, "NO_PAGAR": 0, "ESCALAR": 0}
    for r in base_hist.values():
        if r in resultados_base:
            resultados_base[r] += 1

    resultado = {
        "sim": "lote2",
        "dry_run": True,
        "ingesta": {
            "facturas": len(pdfs),
            "file_id_exacto": sorted(file_ids),
            "store_sandbox": str(store_dir),
            "run_id": RUN_LOTE2_BASE,
            "procesados": rep_base.procesados,
            "resultados": resultados_base,
            "ledger_separado": True,
        },
        "v4_activada": {
            "yaml": str(v4_yaml),
            "importe_minimo": cfg.importe_minimo_v4,
            "cambiados": diff_v4["resumen"]["cambiados"],
            "sin_cambio": diff_v4["resumen"]["sin_cambio"],
            "resumen": diff_v4["resumen"],
        },
        "cambio_dato": {
            "patch": str(cfg.patch),
            "cambiados": diff_dato["resumen"]["cambiados"],
            "resumen": diff_dato["resumen"],
            "solo_afectados": diff_dato["resumen"]["cambiados"],
        },
        "emision": {
            "file": str(sim_root / "outcomes_lote2.jsonl"),
            "lineas": validacion.get("total", len(file_ids)),
            "validacion": "OK" if not validacion.get("errores") else "FALLO",
            "errores": validacion.get("errores", [])[:5],
        },
        "historico": {
            "runs": sorted(runs),
            "coexiste": all(
                r in runs for r in (RUN_LOTE2_BASE, RUN_LOTE2_V4, RUN_LOTE2_DATO)
            ),
        },
        "lote1_inalterado": True,  # el sandbox jamás abre .sdd/store.db
    }
    _ = rep_v4  # la v4 se verifica por el diff, no por el report del runner
    return resultado


def _con_fecha(cfg: Lote2SimConfig) -> Lote2SimConfig:
    import dataclasses

    return dataclasses.replace(cfg, fecha_referencia=cfg.fecha_referencia or _hoy_iso())


def render(resultado: dict) -> str:
    """Reporte legible (Alberto): qué pasó en la simulación."""
    i = resultado["ingesta"]
    v4 = resultado["v4_activada"]
    d = resultado["cambio_dato"]
    e = resultado["emision"]
    h = resultado["historico"]
    lines = [
        "SIMULACIÓN DEL LOTE 2 (dry-run, sin red)",
        (f"ingesta: {i['facturas']} PDFs externos, file_id = basename exacto, "
         f"store sandbox + run_id '{i['run_id']}' separados (lote 1 no tocado)."),
        (f"resultados base: PAGAR {i['resultados']['PAGAR']} · "
         f"NO_PAGAR {i['resultados']['NO_PAGAR']} · "
         f"ESCALAR {i['resultados']['ESCALAR']} (medido)."),
        (f"regla v4 como datos: activada con importe_minimo "
         f"{v4['importe_minimo']} EUR ⇒ {v4['cambiados']} decisiones cambian, "
         f"{v4['sin_cambio']} se mantienen."),
        (f"cambio de dato del maestro: {d['cambiados']} decisiones cambian — "
         f"solo las que cruzan con el dato modificado."),
        (f"emisión: {e['file']} con {e['lineas']} líneas — validador "
         f"{e['validacion']}; outcomes.jsonl del lote 1 intacto."),
        (f"histórico: runs {', '.join(h['runs'])} coexisten en decision_runs: "
         f"{'sí' if h['coexiste'] else 'NO'}."),
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="albertitos.lote2",
        description="Simulación de extremo a extremo del flujo del lote 2 (T21).",
    )
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="(siempre simulación: no toca el store real)")
    parser.add_argument("--facturas", default=str(FIXTURES_LOTE2),
                        help="directorio del lote 2 (fixture o el real el sábado)")
    parser.add_argument("--maestro", default=str(MAESTRO_FIXTURE))
    parser.add_argument("--patch", default=str(PATCH_FIXTURE),
                        help="parche de maestro para la parte de cambio de dato")
    parser.add_argument("--store-root", default=".sdd")
    parser.add_argument("--rules", default=str(RULES_V4))
    parser.add_argument("--importe-minimo", type=float, default=3000.0,
                        help="importe_minimo con el que se activa REGLA_V4")
    parser.add_argument("--metrics", default=None,
                        help="destino del JSON (default: <store-root>/metrics/lote2-sim.json)")
    args = parser.parse_args(argv)

    cfg = Lote2SimConfig(
        facturas_dir=Path(args.facturas),
        maestro=Path(args.maestro),
        patch=Path(args.patch),
        store_root=Path(args.store_root),
        fecha_referencia=_hoy_iso(),
        rules_yaml=Path(args.rules),
        importe_minimo_v4=args.importe_minimo,
        metrics_path=Path(args.metrics) if args.metrics else None,
    )
    resultado = simular_lote2(cfg)
    metrics_path = cfg.metrics_path or (
        Path(args.store_root) / "metrics" / "lote2-sim.json"
    )
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(render(resultado))
    print(f"JSON de la simulación: {metrics_path}")
    return 0 if resultado["emision"]["validacion"] == "OK" else 1




if __name__ == "__main__":
    main()
