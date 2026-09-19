"""Reprocesado dirigido + diff de impacto (T13).

La pieza que hace viable el lote 2 y el cambio de dato del maestro SIN rehacer
todo (AGENTS.md §13: "el reprocesado y su diff deben funcionar desde el
diseño").

Qué hace:
1. Aplica un parche de maestro EN MEMORIA (`--maestro-patch`): `caja-de-
   alberto/` jamás se toca — el parche es un yaml aparte.
2. Determina los archivos AFECTADOS: los que cruzan con el proveedor/pedido/
   NIF/IBAN modificado (según lo guardado en el store: nif, iban, pedido),
   por valor ANTES y DESPUÉS del cambio.
3. Re-ejecuta SOLO los afectados (+ los ESCALAR con `--all-scaled`) con el
   stack completo (escalera→parse→reglas), registrando cada decisión en el
   histórico con run_id distinto: la decisión anterior COEXISTE, jamás se
   sobreescribe (store.decision_runs).
4. Produce el diff de impacto: `.sdd/metrics/impacto.json` + reporte legible.
   Determinista: mismo parche ⇒ mismo diff byte a byte.

Cargar la v3 o la v4 es elegir un archivo yaml — cero cambios de código.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, replace
from pathlib import Path

import yaml

from albertitos.extract.config import ExtractionConfig
from albertitos.rules.master import Maestro
from albertitos.run import Runner, RunnerConfig, _hoy_iso
from albertitos.store import Store, StoredDecision

DEFAULT_FACTURAS = "caja-de-alberto/facturas"
DEFAULT_MAESTRO = "caja-de-alberto/FINAL_v7_DEFINITIVO_ahorasi.xlsx"
DEFAULT_RULES = "src/albertitos/rules/regla_v3.yaml"

RUN_BASE = "base"

_CAMPOS_PROVEEDOR = ("razon_social", "nif", "iban")
_CAMPOS_PEDIDO = ("importe", "estado", "nif", "fecha")


# ---------------------------------------------------------------- parche


def load_patch(path: str | Path) -> dict:
    """Carga y valida un parche de maestro (yaml). Nunca toca el submódulo."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    for section, campos in (
        ("proveedores", _CAMPOS_PROVEEDOR),
        ("pedidos", _CAMPOS_PEDIDO),
    ):
        for pid, cambios in (data.get(section) or {}).items():
            if not isinstance(cambios, dict) or not cambios:
                raise ValueError(f"parche {section}[{pid}]: cambios vacíos")
            desconocidos = set(cambios) - set(campos)
            if desconocidos:
                raise ValueError(
                    f"parche {section}[{pid}]: campos desconocidos "
                    f"{sorted(desconocidos)} (permitidos: {campos})"
                )
    desconocidas = set(data) - {"proveedores", "pedidos"}
    if desconocidas:
        raise ValueError(f"secciones de parche desconocidas: {sorted(desconocidas)}")
    return data


def apply_master_patch(master: Maestro, patch: dict) -> tuple[Maestro, dict]:
    """Aplica el parche SOLO en memoria. Devuelve (maestro_parcheado, resumen).

    El resumen registra qué cambió (provenance del cambio de dato). El sha256
    del maestro NO cambia: el Excel en `caja-de-alberto/` no se modifica.
    """
    prov_nif = dict(master.proveedores_por_nif)
    prov_id = dict(master.proveedores_por_id)
    pedidos = dict(master.pedidos)
    resumen: dict[str, dict] = {"proveedores": {}, "pedidos": {}}

    for pid, cambios in (patch.get("proveedores") or {}).items():
        prov = prov_id.get(pid)
        if prov is None:
            raise ValueError(f"parche: proveedor {pid} no existe en el maestro")
        nuevos: dict[str, str] = {}
        if "razon_social" in cambios:
            nuevos["razon_social"] = str(cambios["razon_social"])
        if "nif" in cambios:
            nuevos["nif"] = str(cambios["nif"]).upper().replace(" ", "")
        if "iban" in cambios:
            nuevos["iban"] = str(cambios["iban"]).upper().replace(" ", "")
        antes = {"razon_social": prov.razon_social, "nif": prov.nif,
                 "iban": prov.iban}
        resumen["proveedores"][pid] = {"antes": antes, "despues": {**antes, **nuevos}}
        prov_nuevo = replace(prov, **nuevos)
        prov_id[pid] = prov_nuevo
        if prov.nif != prov_nuevo.nif:
            prov_nif.pop(prov.nif, None)
        prov_nif[prov_nuevo.nif] = prov_nuevo

    for pid, cambios in (patch.get("pedidos") or {}).items():
        ped = pedidos.get(pid)
        if ped is None:
            raise ValueError(f"parche: pedido {pid} no existe en el maestro")
        nuevos: dict[str, object] = {}
        if "importe" in cambios:
            nuevos["importe"] = float(cambios["importe"])
        if "estado" in cambios:
            nuevos["estado"] = str(cambios["estado"]).strip().upper()
        if "nif" in cambios:
            nuevos["nif"] = str(cambios["nif"]).upper().replace(" ", "")
        if "fecha" in cambios:
            nuevos["fecha"] = str(cambios["fecha"])
        antes = {"importe": ped.importe, "estado": ped.estado,
                 "nif": ped.nif, "fecha": ped.fecha}
        resumen["pedidos"][pid] = {"antes": antes, "despues": {**antes, **nuevos}}
        pedidos[pid] = replace(ped, **nuevos)

    parcheado = Maestro(
        proveedores_por_nif=prov_nif,
        proveedores_por_id=prov_id,
        pedidos=pedidos,
        pedidos_en_revision=master.pedidos_en_revision,
        hojas_ignoradas=master.hojas_ignoradas,
        duplicados_deducidos=master.duplicados_deducidos,
        sha256=master.sha256,
        avisos=master.avisos + ("parche_aplicado_en_memoria",),
    )
    return parcheado, resumen


# ---------------------------------------------------------------- afectados


def affected_files(store: Store, master: Maestro, patch: dict,
                   pdfs: set[str]) -> tuple[str, ...]:
    """Archivos que cruzan con lo modificado por el parche.

    Criterio exacto, sobre lo que el store guardó a la hora de decidir:
    - pedido modificado ⇒ facturas con ese pedido;
    - proveedor modificado ⇒ facturas cuyo NIF o IBAN coincide con el valor
      ANTES (maestro en disco) o DESPUÉS (parche) del cambio.
    Resultado ordenado por file_id (determinismo).
    """
    afectados: set[str] = set()
    pedidos_mod = set(patch.get("pedidos") or {})
    nifs: set[str] = set()
    ibans: set[str] = set()
    for cambios in (patch.get("proveedores") or {}).values():
        if "nif" in cambios:
            nifs.add(str(cambios["nif"]).upper().replace(" ", ""))
        if "iban" in cambios:
            ibans.add(str(cambios["iban"]).upper().replace(" ", ""))
    for pid in patch.get("proveedores") or {}:
        prov = master.proveedores_por_id.get(pid)
        if prov is not None:  # valores ANTES
            nifs.add(prov.nif)
            ibans.add(prov.iban)
    for d in store.all_decisions():
        if d.pedido and d.pedido in pedidos_mod:
            afectados.add(d.file_id)
        if d.nif and d.nif in nifs:
            afectados.add(d.file_id)
        if d.iban and d.iban in ibans:
            afectados.add(d.file_id)
    return tuple(sorted(afectados & pdfs))


def scaled_files(store: Store, pdfs: set[str]) -> tuple[str, ...]:
    """Todos los file_id con resultado actual ESCALAR (orden determinista)."""
    return tuple(sorted(
        d.file_id for d in store.all_decisions()
        if d.result == "ESCALAR" and d.file_id in pdfs
    ))


# ---------------------------------------------------------------- reprocesado


def reprocesar(cfg: ReprocessConfig) -> dict:
    """Re-ejecuta SÓLO los afectados con run_id propio y calcula el diff."""
    store = Store(cfg.store_root)
    try:
        pdfs = {p.name for p in Path(cfg.facturas_dir).glob("*.pdf")}
        # affected-set: maestro SIN parchear para los valores ANTES
        from albertitos.rules import load_config, load_master

        ecfg = load_config(cfg.rules_yaml, fecha_referencia=cfg.fecha_referencia)
        master_pre = load_master(cfg.master_path, hojas_ignoradas=ecfg.hojas_ignoradas)

        objetivo: set[str] = set(cfg.files)
        if cfg.patch is not None:
            objetivo |= set(affected_files(store, master_pre, cfg.patch, pdfs))
        if cfg.all_scaled:
            objetivo |= set(scaled_files(store, pdfs))
        objetivo &= pdfs
        objetivo = set(objetivo)
        if not objetivo:
            raise ValueError(
                "nada que reprocesar: 0 afectados. Indica --maestro-patch, "
                "--all-scaled o --files."
            )

        runner_cfg = RunnerConfig(
            facturas_dir=Path(cfg.facturas_dir),
            outcomes_path=Path(cfg.outcomes_path or "outcomes.jsonl"),
            store_root=Path(cfg.store_root),
            rules_yaml=Path(cfg.rules_yaml),
            master_path=cfg.master_path,
            fecha_referencia=cfg.fecha_referencia,
            use_rung4=cfg.use_rung4,
            extract_config=cfg.extract_config,
            force=True,  # reprocesar aunque la decisión exista
            run_id=cfg.run_id,
            maestro_patch=cfg.patch_path,
            only_list=tuple(sorted(objetivo)),
        )
        runner = Runner(runner_cfg)
        if cfg.patch is not None:
            parcheado, resumen_parche = apply_master_patch(
                runner.master, cfg.patch)
            runner.master = parcheado
            runner.patch_resumen = resumen_parche
        report = runner.run()

        impacto = diff_runs(store, cfg.base_run, cfg.run_id)
        impacto["resumen"]["reprocesados"] = report.procesados
        impacto["resumen"]["objetivo"] = len(objetivo)
        return impacto
    finally:
        store.close()


# ---------------------------------------------------------------- diff


def _regla_responsable(d: StoredDecision) -> str:
    """Código de la regla que decidió: primera anomaly UNKNOWN, luego gate FAIL."""
    preferidas: list[str] = []
    for code_out in d.rule_codes:
        if ":" not in code_out:
            continue
        code, outcome = code_out.rsplit(":", 1)
        if outcome == "UNKNOWN" or outcome == "FAIL":
            preferidas.append(code)
    if preferidas:
        return preferidas[0]
    return (d.rule_codes[0].rsplit(":", 1)[0] if d.rule_codes else "")


def _config_version_de(run: dict[str, StoredDecision]) -> str:
    """config_version del run (todas las decisiones comparten config)."""
    for fid in sorted(run):
        return run[fid].config_version
    return ""


def diff_runs(store: Store, run_base: str = RUN_BASE,
              run_nuevo: str = "") -> dict:
    """Diff determinista entre dos runs del histórico (T13).

    Sin timestamps ni números aleatorios: mismo contenido ⇒ mismo JSON byte a
    byte. La UI (Facturas/Reglas) lee esta estructura.
    """
    antes = {d.file_id: d for d in store.run_decisions(run_base)}
    despues = {d.file_id: d for d in store.run_decisions(run_nuevo)}
    # El diff compara lo presente en AMBOS runs (lo efectivamente reprocesado);
    # lo que solo está en uno se informa aparte, nunca como "cambio".
    ids = sorted(set(antes) & set(despues))
    solo_base = sorted(set(antes) - set(despues))
    solo_nuevo = sorted(set(despues) - set(antes))
    cambios: list[dict] = []
    sin_cambio = 0
    escalados_antes = sum(1 for d in antes.values() if d.result == "ESCALAR")
    escalados_despues = sum(1 for d in despues.values() if d.result == "ESCALAR")
    for fid in ids:
        a, b = antes[fid], despues[fid]
        if a.result != b.result:
            cambios.append({
                "file_id": fid,
                "antes": a.result,
                "despues": b.result,
                "regla": _regla_responsable(b),
                "config_version": b.config_version,
            })
        else:
            sin_cambio += 1
    return {
        "run_base": run_base,
        "run_nuevo": run_nuevo,
        "config_version_base": _config_version_de(antes),
        "config_version_nuevo": _config_version_de(despues),
        "resumen": {
            "afectados": len(ids),
            "solo_en_run_base": len(solo_base),
            "solo_en_run_nuevo": len(solo_nuevo),
            "cambiados": len(cambios),
            "sin_cambio": sin_cambio,
            "escalados_antes": escalados_antes,
            "escalados_despues": escalados_despues,
        },
        "cambios": cambios,
    }


def write_impact(impacto: dict, metrics_dir: str | Path) -> tuple[Path, Path]:
    """Escribe impacto.json (máquina, la UI lo lee) + impacto.txt (legible)."""
    root = Path(metrics_dir)
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / "impacto.json"
    json_path.write_text(
        json.dumps(impacto, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    txt_path = root / "impacto.txt"
    txt_path.write_text(render_impact(impacto), encoding="utf-8")
    return json_path, txt_path


def metrics_dir_path(store_root: str | Path = ".sdd") -> str:
    return str(Path(store_root) / "metrics")


def render_impact(impacto: dict) -> str:
    """Reporte legible en español llano (Alberto): qué cambió y por qué."""
    r = impacto["resumen"]
    lines = [
        "IMPACTO DEL REPROCESADO",
        f"run anterior: {impacto['run_base']}  →  run nuevo: {impacto['run_nuevo']}",
        (f"afectados: {r['afectados']} (medido) · cambiados: {r['cambiados']} · "
         f"sin cambio: {r['sin_cambio']}"),
        (f"escalados antes: {r['escalados_antes']} · escalados después: "
         f"{r['escalados_despues']} (medido)"),
        "",
    ]
    for c in impacto["cambios"]:
        lines.append(
            f"- {c['file_id']}: {c['antes']} → {c['despues']} "
            f"(regla: {c['regla'] or 'n/d'})"
        )
    if not impacto["cambios"]:
        lines.append("Ningún resultado cambió.")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- config/CLI


@dataclass(frozen=True)
class ReprocessConfig:
    facturas_dir: Path
    store_root: Path
    rules_yaml: Path
    master_path: Path
    fecha_referencia: str
    patch_path: Path | None = None
    patch: dict | None = None
    all_scaled: bool = False
    files: tuple[str, ...] = ()
    run_id: str = "repro"
    base_run: str = RUN_BASE
    use_rung4: bool = False
    # T24: config de extracción inyectable (drill del rung 4).
    extract_config: ExtractionConfig | None = None
    outcomes_path: Path | None = None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="albertitos.reprocess",
        description="Reprocesado dirigido + diff de impacto (T13).",
    )
    parser.add_argument("--facturas", default=DEFAULT_FACTURAS)
    parser.add_argument("--store-root", default=".sdd")
    parser.add_argument("--rules", default=DEFAULT_RULES,
                        help="yaml de reglas (v3 o v4: elegir archivo)")
    parser.add_argument("--maestro", default=DEFAULT_MAESTRO)
    parser.add_argument("--fecha-referencia", default=_hoy_iso())
    parser.add_argument("--maestro-patch", default=None,
                        help="yaml con el cambio de dato (en memoria)")
    parser.add_argument("--all-scaled", action="store_true",
                        help="reprocesar también todos los ESCALAR actuales")
    parser.add_argument("--files", default="",
                        help="file_ids extra a reprocesar, separados por coma")
    parser.add_argument("--run-id", default="repro")
    parser.add_argument("--base-run", default=RUN_BASE)
    parser.add_argument("--outcomes", default="outcomes.jsonl",
                        help="emite outcomes.jsonl actualizado tras reprocesar")
    parser.add_argument("--use-rung4", action="store_true")
    parser.add_argument("--no-diff", action="store_true")
    args = parser.parse_args(argv)

    patch_path = Path(args.maestro_patch) if args.maestro_patch else None
    patch = load_patch(patch_path) if patch_path else None
    files = tuple(f for f in (s.strip() for s in args.files.split(",")) if f)
    cfg = ReprocessConfig(
        facturas_dir=Path(args.facturas),
        store_root=Path(args.store_root),
        rules_yaml=Path(args.rules),
        master_path=Path(args.maestro),
        fecha_referencia=args.fecha_referencia,
        patch_path=patch_path,
        patch=patch,
        all_scaled=args.all_scaled,
        files=files,
        run_id=args.run_id,
        base_run=args.base_run,
        use_rung4=args.use_rung4,
        outcomes_path=Path(args.outcomes) if args.outcomes else None,
    )
    impacto = reprocesar(cfg)

    if args.outcomes:
        from albertitos.emit import emit_outcomes

        emit_outcomes(Store(args.store_root), args.outcomes)
    if not args.no_diff:
        json_path, txt_path = write_impact(
            impacto, metrics_dir_path(args.store_root))
        print(txt_path.read_text(encoding="utf-8"))
        print(f"diff máquina: {json_path}")
        print(f"reporte legible: {txt_path}")
    return 0