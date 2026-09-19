"""Runner de lote end-to-end (T8): los 500 PDFs → outcomes.jsonl.

Orquesta el stack completo: escalera de extracción por página (T1) → parser
(T2) → motor de reglas (T3) → store + evidencia (T4) → emisión + validador
de contrato (T9). Es producto, no glue de debug.

Reglas duras (ticket T8):
- `caja-de-alberto/` NUNCA se toca (solo lectura).
- Timeout por archivo: un archivo colgado ⇒ ESCALAR con motivo `timeout` +
  evidencia, y el lote sigue. Presupuesto medido desde la entrada en cola
  (procesando o esperando slot tras un colgado).
- Concurrencia: máximo 2 archivos en vuelo. Si llama-server (rung 4) está
  UP tras health-check, TODO el lote va en cola SECUENCIAL (1 en vuelo):
  el rung 4 nunca corre en paralelo con el resto (8 cores compartidos).
- Reanudable: salta lo completado (fila de decisión + cache por file_id);
  crash a mitad ⇒ re-run completa sin duplicados.
- Progreso visible en `.sdd/state/runner.json` (la UI T5 lo lee).
"""

from __future__ import annotations

import argparse
import dataclasses
import fnmatch
import json
import os
import time
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from albertitos.emit import emit_outcomes, list_pdf_files
from albertitos.extract.cloud import cloud_config_from_env
from albertitos.extract.config import ExtractionConfig
from albertitos.extract.ladder import ExtractionLadder
from albertitos.parse.normalizers import parse_amount_float
from albertitos.parse.parser import parse_invoice
from albertitos.rules import BatchContext, decide, load_config, load_master
from albertitos.rules.config import EngineConfig
from albertitos.rules.master import Maestro
from albertitos.store import Store, invoice_uuid
from albertitos.types import (
    Candidate,
    Decision,
    EvidenceRow,
    ExtractionFeature,
    ExtractionField,
    RuleVerdict,
)

ENGINE_VERSION = "runner-1.1.0"  # 1.1.0: ADR-06, selección de candidato con provenance (T18)
STAGE_RUN = "run"
CODE_TIMEOUT = "RUNNER_TIMEOUT"

# Campos cuyo valor el motor compara como NÚMERO (los candidatos del parser
# son float para estos tipos); un override humano llega como TEXTO de la UI.
_CAMPOS_NUMERICOS = frozenset({"base", "iva_pct", "iva_amount", "total"})


def aplicar_overrides(
    fields: list[ExtractionField], overrides: list[dict]
) -> tuple[list[ExtractionField], list[dict], list[dict]]:
    """Inyecta overrides humanos como candidatos de extracción (T38-F6).

    AGENTS.md §7: el override alimenta SOLO la extracción — un candidato
    `extractor="humano"`, conf 1.0 y provenance `override:<cuando>` — y la
    decisión la recalcula SIEMPRE el motor determinista. El override nunca
    decide.

    Devuelve (fields, aplicados, descartados). Los descartados (valor vacío
    o no convertible a número en campos numéricos) NO se pierden en
    silencio: el runner deja fila de evidencia por cada uno.
    """
    if not overrides:
        return fields, [], []
    por_tipo = {f.type: f for f in fields}
    nuevos: dict[str, Candidate] = {}
    aplicados: list[dict] = []
    descartados: list[dict] = []
    for ov in overrides:
        campo = str(ov.get("campo") or "").strip()
        valor = ov.get("valor")
        if not campo or valor is None or str(valor).strip() == "":
            descartados.append(ov)
            continue
        texto = str(valor).strip()
        if campo in _CAMPOS_NUMERICOS:
            num = parse_amount_float(texto)
            if num is None:
                descartados.append(ov)
                continue
            value: str | float = num
        else:
            value = texto
        nuevos[campo] = Candidate(
            extractor="humano",
            value=value,
            confidence=1.0,
            feature_ref=f"override:{ov.get('cuando', '')}",
        )
        aplicados.append(ov)
    for campo, cand in nuevos.items():  # un override por campo: el último gana
        f = por_tipo.get(campo)
        if f is not None:
            f.values.append(cand)
        else:
            nf = ExtractionField(type=campo, timestamp=time.time(), values=[cand])
            fields.append(nf)
            por_tipo[campo] = nf
    return fields, aplicados, descartados

DEFAULT_FACTURAS = "caja-de-alberto/facturas"
DEFAULT_MAESTRO = "caja-de-alberto/FINAL_v7_DEFINITIVO_ahorasi.xlsx"
DEFAULT_RULES = "src/albertitos/rules/regla_v3.yaml"


@dataclass(frozen=True)
class RunnerConfig:
    facturas_dir: Path
    outcomes_path: Path
    store_root: Path
    rules_yaml: Path
    master_path: Path
    fecha_referencia: str
    timeout_por_archivo_s: float = 120.0
    max_in_flight: int = 2
    limit: int | None = None
    only: str | None = None  # glob sobre el basename exacto
    only_list: tuple[str, ...] | None = None  # subset exacto de file_ids (T13)
    use_rung4: bool = True  # False = tests / degradación manual (no billing)
    force: bool = False  # T13: re-ejecutar aunque la decisión exista
    run_id: str = "base"  # T13: run del histórico en decision_runs
    emit_scope: str = "todo"  # "todo" (lote 1) | "lote" (lote 2: solo sus file_id)
    maestro_patch: Path | None = None  # T13: parche de maestro EN MEMORIA
    # T24 (drill): config de extracción inyectable (vlm_base_url del stub,
    # umbrales que fuerzan tráfico al rung 4). None ⇒ la default.
    extract_config: ExtractionConfig | None = None


@dataclass
class RunReport:
    total: int = 0
    procesados: int = 0
    reutilizados: int = 0
    timeout: int = 0
    fallos: int = 0
    resultados: dict[str, str] = field(default_factory=dict)
    elapsed_s: float = 0.0
    files_per_second: float = 0.0  # medido
    workers: int = 1
    rung4_secuencial: bool = False
    validacion: dict | None = None


def _vlm_up(base_url: str, timeout_s: float = 2.0, *,
            ready: bool = False) -> bool:
    """Health del VLM local (llama-server, OpenAI-compatible).

    ready=False (default): solo /v1/models — para saber si el rung 4 está
    CONFIGURADO (durante la carga del modelo las llamadas quedan en cola;
    eso lo acota el presupuesto por archivo, T8/T24).

    ready=True (T29): listo DE VERDAD — exige además `GET /health == 200`.
    Durante la carga /health contesta 503 (HTTPError ⇒ False). Es el fix del
    race documentado en T24: ni el drill ni nadie debe actuar "como listo"
    con el modelo a medias, y un servidor colgado (acepta y no responde)
    tampoco es listo.
    """
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(
            base_url.rstrip("/") + "/v1/models", timeout=timeout_s
        ) as resp:
            if resp.status != 200:
                return False
    except (urllib.error.URLError, OSError, TimeoutError, ValueError):
        return False
    if not ready:
        return True
    try:
        with urllib.request.urlopen(
            base_url.rstrip("/") + "/health", timeout=timeout_s
        ) as resp:
            return resp.status == 200
    except (urllib.error.HTTPError, urllib.error.URLError, OSError,
            TimeoutError, ValueError):
        return False  # 503 de carga, colgado o caído: NO listo




class Runner:
    """Runner end-to-end, reanudable y medido. Nunca escribe en el corpus."""

    def __init__(self, cfg: RunnerConfig) -> None:
        self.cfg = cfg
        self.ecfg: EngineConfig = load_config(
            cfg.rules_yaml, fecha_referencia=cfg.fecha_referencia
        )
        self.master: Maestro = load_master(
            cfg.master_path, hojas_ignoradas=self.ecfg.hojas_ignoradas
        )
        self.store = Store(cfg.store_root)
        self.state_path = cfg.store_root / "state" / "runner.json"
        xcfg = cfg.extract_config if cfg.extract_config is not None else ExtractionConfig()
        if not cfg.use_rung4:
            # Puerto que rechaza al instante: el health-check del rung 4
            # falla sin esperar (degradación determinista en tests).
            xcfg = dataclasses.replace(xcfg, vlm_base_url="http://127.0.0.1:1")
        cloud = cloud_config_from_env()  # None si env incompleto ⇒ skip reason
        self.ladder = ExtractionLadder(
            cfg=xcfg,
            cache_root=cfg.store_root / "cache",
            review_dir=cfg.store_root / "review-queue",
            cloud=cloud,
        )
        self.rung4_disponible = cfg.use_rung4 and _vlm_up(xcfg.vlm_base_url)
        # T13: parche de maestro en memoria (el Excel del submódulo no se toca)
        self.patch_resumen: dict | None = None
        if cfg.maestro_patch is not None:
            from albertitos.reprocess import apply_master_patch, load_patch

            self.master, self.patch_resumen = apply_master_patch(
                self.master, load_patch(cfg.maestro_patch))
        # Costuras de prueba (None en producción): un hook que lanza simula
        # crash; un hook que duerme simula archivo colgado.
        self.fail_hook = None
        self.sleep_hook = None
        self._deadline: dict[str, float] = {}

    # ------------------------------------------------------------ enumeración

    def files(self) -> list[Path]:
        files = list_pdf_files(self.cfg.facturas_dir)
        if self.cfg.only:
            files = [p for p in files if fnmatch.fnmatch(p.name, self.cfg.only)]
        if self.cfg.only_list is not None:
            wanted = set(self.cfg.only_list)
            files = [p for p in files if p.name in wanted]
        if self.cfg.limit is not None:
            files = files[: self.cfg.limit]
        return files

    def max_workers(self) -> int:
        # Rung 4 UP ⇒ cola SECUENCIAL (una página cada vez, nunca en paralelo).
        return 1 if self.rung4_disponible else max(1, min(2, self.cfg.max_in_flight))

    # ------------------------------------------------------------ ejecución

    def run(self) -> RunReport:
        report = RunReport()
        files = self.files()
        report.total = len(files)
        workers = self.max_workers()
        report.workers = workers
        report.rung4_secuencial = self.rung4_disponible

        # Contexto previo del lote (reanudación): determinismo por orden de
        # file_id ascendente; la DECISIÓN se toma siempre en el hilo principal.
        # T13/T21: si se está RE-DECIDIENDO un subset (force/only_list), sus
        # decisiones antiguas NO cuentan como "ya vistas" (un re-run no debe
        # convertirse en falso doble pago contra sí mismo).
        if self.cfg.force:
            excl = {p.name for p in files}
        else:
            excl = (set(self.cfg.only_list)
                    if self.cfg.only_list is not None else None)
        prev_num = {d.numero_factura: d.file_id
                    for d in self.store.all_decisions()
                    if d.numero_factura
                    and (excl is None or d.file_id not in excl)}
        prev_pedidos = {d.pedido for d in self.store.all_decisions()
                        if d.result == "PAGAR" and d.pedido
                        and (excl is None or d.file_id not in excl)}

        started = time.monotonic()
        pool = ThreadPoolExecutor(max_workers=workers)
        futures: dict[str, Future] = {}
        try:
            # Presupuesto de timeout desde el ARRANQUE REAL de cada archivo
            # (lo fija _task al empezar a ejecutarse). Medido en el drill T24:
            # con presupuesto desde ENTRADA EN COLA y rung 4 secuencial, la
            # cola de recuperación genera falsos RUNNER_TIMEOUT en cascada
            # (los archivos esperan en cola > timeout sin haber empezado). Si
            # un archivo nunca arranca, el presupuesto de espera también ⇒
            # ESCALAR timeout y el lote sigue.
            for path in files:
                futures[path.name] = pool.submit(self._task, path)
            for path in files:
                sha256 = _sha256_file(path)
                invoice_id = invoice_uuid(sha256)
                done = self.store.decision_for(path.name)
                if not self.cfg.force and done and done.engine_version == ENGINE_VERSION \
                        and done.config_version == self.ecfg.config_version:
                    report.reutilizados += 1
                    report.resultados[path.name] = done.result
                    self._tick_state(files, report, started)
                    continue
                fut = futures[path.name]
                try:
                    remaining = _esperar_arranque(fut, self._deadline.get,
                                                  path.name,
                                                  self.cfg.timeout_por_archivo_s)
                    if remaining <= 0:
                        raise FuturesTimeout()
                    extracted = fut.result(timeout=remaining)
                    resultado = self._decide_and_record(
                        path, extracted, prev_num, prev_pedidos)[0]
                    report.procesados += 1
                except FuturesTimeout:
                    resultado = self._record_timeout(path, sha256, invoice_id)
                    report.timeout += 1
                    report.procesados += 1
                report.resultados[path.name] = resultado
                self._tick_state(files, report, started)
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
            report.elapsed_s = time.monotonic() - started
            done_count = report.procesados + report.reutilizados
            report.files_per_second = (
                round(done_count / report.elapsed_s, 3)
                if report.elapsed_s > 0 else 0.0
            )
            self._write_state(files, report)
        return report

    # ------------------------------------------------------------ etapas

    def _task(self, path: Path):
        """Trabajo pesado (extracción): puede colgar ⇒ timeout lo captura.

        El presupuesto arranca con el primer instante de ejecución real."""
        self._deadline[path.name] = time.monotonic() + self.cfg.timeout_por_archivo_s
        if self.sleep_hook is not None:
            self.sleep_hook(path.name)
        if self.fail_hook is not None:
            self.fail_hook(path.name)
        return self._extract(path)

    def _extract(self, path: Path) -> dict:
        sha256 = _sha256_file(path)
        invoice_id = invoice_uuid(sha256)
        pages = self.ladder.extract_file(
            path, invoice_id=invoice_id, file_id=path.name
        )
        features: list[ExtractionFeature] = []
        evidence: list[EvidenceRow] = []
        for pg in pages:
            features.extend(pg.features)
            for row in pg.evidence:
                row.file_id = path.name
                evidence.append(row)
        rungs_usados = ",".join(sorted({pg.final_rung for pg in pages}))
        return {
            "sha256": sha256,
            "invoice_id": invoice_id,
            "features": features,
            "evidence": evidence,
            "rungs": rungs_usados,
        }

    def _decide_and_record(self, path: Path, extracted: dict,
                           prev_num: dict, prev_pedidos: set) -> tuple[str, str]:
        sha256 = extracted["sha256"]
        invoice_id = extracted["invoice_id"]
        features = extracted["features"]
        for row in extracted["evidence"]:
            self.store.record_evidence(row)

        started = time.monotonic()
        fields = parse_invoice(features)
        self.store.record_evidence(EvidenceRow(
            file_id=path.name, invoice_id=invoice_id, stage="parse",
            extractor="parser", extractor_version=ENGINE_VERSION,
            config_version=self.ecfg.config_version, sha256=sha256,
            latency_ms=int((time.monotonic() - started) * 1000),
            confidence=None, outcome="ok" if fields else "empty",
            detail=",".join(sorted(f.type for f in fields)),
        ))

        # Overrides humanos pendientes de este file_id → candidatos de
        # extracción; la decisión la recalcula el motor (T38-F6, §7).
        pendientes = [
            o
            for o in self.ladder.review.read_overrides_pendientes()
            if o.get("file_id") == path.name
        ]
        fields, aplicados, descartados = aplicar_overrides(fields, pendientes)
        for ov in aplicados:
            self.store.record_evidence(EvidenceRow(
                file_id=path.name, invoice_id=invoice_id, stage="override",
                extractor="humano", extractor_version=ENGINE_VERSION,
                config_version=self.ecfg.config_version, sha256=sha256,
                latency_ms=0, confidence=1.0, outcome="aplicado",
                detail=f"{ov.get('campo')}={ov.get('valor')}",
            ))
        for ov in descartados:
            self.store.record_evidence(EvidenceRow(
                file_id=path.name, invoice_id=invoice_id, stage="override",
                extractor="humano", extractor_version=ENGINE_VERSION,
                config_version=self.ecfg.config_version, sha256=sha256,
                latency_ms=0, confidence=None, outcome="descartado",
                detail=f"{ov.get('campo')}={ov.get('valor')}: no convertible",
            ))

        textos = tuple(str(f.data) for f in features if isinstance(f.data, str))
        decision = decide(
            fields, textos, self.master, self.ecfg,
            BatchContext(facturas_vistas=dict(prev_num),
                         pedidos_pagados=frozenset(prev_pedidos)),
            invoice_id=invoice_id, file_id=path.name,
        )
        numero = _mejor_valor(fields, "numero_factura")
        pedido = _mejor_valor(fields, "pedido")
        nif = _mejor_valor(fields, "nif")
        iban = _mejor_valor(fields, "iban")
        self.store.record_decision(
            decision, sha256, numero_factura=numero, pedido=pedido,
            nif=nif, iban=iban,
            engine_version=ENGINE_VERSION, run_id=self.cfg.run_id,
        )
        self.store.record_evidence(EvidenceRow(
            file_id=path.name, invoice_id=invoice_id, stage="decision",
            extractor="rule-engine", extractor_version=ENGINE_VERSION,
            config_version=self.ecfg.config_version, sha256=sha256,
            latency_ms=int((time.monotonic() - started) * 1000),
            confidence=None, outcome=decision.result,
            detail=",".join(f"{v.code}:{v.outcome}" for v in decision.rule_verdicts),
        ))
        self.store.put_cached(sha256, STAGE_RUN, ENGINE_VERSION,
                              self.ecfg.config_version,
                              {"result": decision.result,
                               "invoice_id": invoice_id,
                               "rungs": extracted["rungs"]})
        if decision.result == "PAGAR" and pedido:
            prev_pedidos.add(pedido)
        if numero:
            prev_num[numero] = path.name
        if pendientes:
            # Marcar consumidos SOLO tras decidir: un crash antes de aquí
            # re-inyecta el override en el re-run (misma decisión byte a
            # byte — el motor es determinista) y vuelve a marcar.
            self.ladder.review.marcar_consumidas(aplicados + descartados)
        return decision.result, decision.config_snapshot.get("motivo", "")

    def _record_timeout(self, path: Path, sha256: str, invoice_id: str) -> str:
        """Timeout ⇒ ESCALAR con motivo `timeout` + evidencia. El lote sigue."""
        verdict = RuleVerdict(
            code=CODE_TIMEOUT, outcome="UNKNOWN",
            reason=f"timeout del archivo ({self.cfg.timeout_por_archivo_s:.0f}s)",
            consumed={"budget_desde_cola": self.cfg.timeout_por_archivo_s},
        )
        snapshot = self.ecfg.snapshot()
        snapshot["motivo"] = "timeout"
        decision = Decision(
            invoice_id=invoice_id, file_id=path.name, result="ESCALAR",
            rule_verdicts=[verdict], config_snapshot=snapshot,
        )
        self.store.record_decision(
            decision, sha256, numero_factura="", pedido="",
            engine_version=ENGINE_VERSION, run_id=self.cfg.run_id,
        )
        self.store.record_evidence(EvidenceRow(
            file_id=path.name, invoice_id=invoice_id, stage="decision",
            extractor="runner", extractor_version=ENGINE_VERSION,
            config_version=self.ecfg.config_version, sha256=sha256,
            latency_ms=int(self.cfg.timeout_por_archivo_s * 1000),
            confidence=None, outcome="ESCALAR",
            detail="timeout: presupuesto por archivo agotado",
        ))
        return "ESCALAR"

    # ------------------------------------------------------------ estado UI

    def _tick_state(self, files: list[Path], report: RunReport,
                    started: float) -> None:
        self._write_state(files, report, started)

    def _write_state(self, files: list[Path], report: RunReport,
                     started: float | None = None) -> None:
        """Estado para la UI (T5): números medidos, nunca estimados.

        T33-M2: un SELECT por tick (era O(N²): decision_for por archivo)."""
        resultados: dict[str, int] = {"PAGAR": 0, "NO_PAGAR": 0, "ESCALAR": 0}
        mapa = self.store.resultados_por_file([p.name for p in files])
        done = len(mapa)
        for result in mapa.values():
            if result in resultados:
                resultados[result] += 1
        elapsed = time.monotonic() - started if started else report.elapsed_s
        state = {
            "actualizado": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
            "medido": True,
            "total_archivos": len(files),
            "done": done,
            "pendientes": max(0, len(files) - done),
            "fallos": report.fallos,
            "timeout": report.timeout,
            "resultados": resultados,
            "files_per_second": (round(done / elapsed, 3) if elapsed > 0 else None),
            "concurrency": report.workers,
            "rung4_llama_server": "up" if self.rung4_disponible else "down",
            "rung4_secuencial": report.rung4_secuencial,
            "timeout_por_archivo_s": self.cfg.timeout_por_archivo_s,
            "engine_version": ENGINE_VERSION,
            "config_version": self.ecfg.config_version,
            "facturas_dir": str(self.cfg.facturas_dir),
        }
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True),
                       encoding="utf-8")
        os.replace(tmp, self.state_path)


# ------------------------------------------------------------ helpers


def _esperar_arranque(fut: Future, deadline_get, file_id: str,
                      timeout_s: float) -> float:
    """Espera (acotada) a que el archivo EMPIECE de verdad y devuelve el
    presupuesto restante. Sin carreras: el worker fija el deadline como
    primera acción; si nunca arranca (cola bloqueada por un colgado) ⇒
    timeout ⇒ ESCALAR y el lote sigue (T24)."""
    t0 = time.monotonic()
    while True:
        deadline = deadline_get(file_id)
        if deadline is not None:
            return deadline - time.monotonic()
        if time.monotonic() - t0 >= timeout_s:
            return 0.0
        time.sleep(0.02)


def _hoy_iso() -> str:
    """Fecha de referencia por defecto: hoy UTC (el motor sigue siendo puro)."""
    return datetime.now(tz=UTC).date().isoformat()


def _sha256_file(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mejor_valor(fields: list, tipo: str) -> str:
    for f in fields:
        if f.type == tipo and f.values:
            best = max(f.values, key=lambda c: c.confidence)
            return str(best.value)
    return ""


# ------------------------------------------------------------ CLI


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="albertitos.run",
        description="Runner de lote end-to-end: PDFs → outcomes.jsonl (T8).",
    )
    parser.add_argument("--facturas", default=DEFAULT_FACTURAS)
    parser.add_argument("--outcomes", default="outcomes.jsonl")
    parser.add_argument("--store-root", default=".sdd")
    parser.add_argument("--rules", default=DEFAULT_RULES)
    parser.add_argument("--maestro", default=DEFAULT_MAESTRO)
    parser.add_argument("--fecha-referencia", default=_hoy_iso(),
                        help="fecha contra la que se juzga 'futura' (motor puro)")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--only", default=None, help="glob sobre el basename")
    parser.add_argument("--run-id", default="base",
                        help="run del histórico (lote 2 ⇒ lote2)")
    parser.add_argument("--timeout", type=float, default=120.0,
                        help="timeout por archivo en segundos")
    parser.add_argument("--max-in-flight", type=int, default=2)
    parser.add_argument("--emit-scope", default="todo", choices=["todo", "lote"],
                        help="emisión: 'todo' el store (lote 1) o solo este "
                             "lote (lote 2 → outcomes_lote2.jsonl)")
    args = parser.parse_args(argv)

    cfg = RunnerConfig(
        facturas_dir=Path(args.facturas),
        outcomes_path=Path(args.outcomes),
        store_root=Path(args.store_root),
        rules_yaml=Path(args.rules),
        master_path=Path(args.maestro),
        fecha_referencia=args.fecha_referencia,
        timeout_por_archivo_s=args.timeout,
        max_in_flight=args.max_in_flight,
        limit=args.limit,
        only=args.only,
        run_id=args.run_id,
        emit_scope=args.emit_scope,
    )
    runner = Runner(cfg)
    report = runner.run()

    # Emisión final + validador de contrato (T9) en verde. Con scope 'lote'
    # el JSONL queda limitado a los file_id de ESTE directorio (lote 2).
    scope = ({p.name for p in runner.files()}
             if args.emit_scope == "lote" else None)
    emit_outcomes(runner.store, cfg.outcomes_path, only_files=scope)
    lote_completo = report.total == len(list_pdf_files(cfg.facturas_dir))
    validacion = None
    if lote_completo:
        from albertitos.validate import validar

        validacion = validar(Path(cfg.outcomes_path), Path(cfg.facturas_dir))

    # Resumen en español llano, números medidos (AGENTS.md §9).
    print(f"Lote: {report.total} archivos · done {report.procesados + report.reutilizados} "
          f"(reutilizados {report.reutilizados}) · timeouts {report.timeout} · "
          f"medido {report.files_per_second} files/s")
    print(f"Rung 4 (llama-server): {'UP — lote secuencial' if report.rung4_secuencial else 'down — degradado a rung 3'}")
    if validacion is not None:
        errores = validacion.get("errores", [])
        print(f"Validador de contrato: {'OK' if not errores else f'{len(errores)} errores'}")
        runner.store.close()
        return 0 if not errores else 1
    print("Validador: OMITIDO (lote parcial — --limit/--only)")
    runner.store.close()
    return 0


if __name__ == "__main__":  # python -m albertitos.run
    raise SystemExit(main())
