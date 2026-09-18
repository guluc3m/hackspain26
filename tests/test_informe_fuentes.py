"""T11 — el informe se alimenta de datos generados, jamás hardcodeados.

El binario typst NO participa en tests: aquí se valida que la plantilla
importa los ficheros de datos generados desde el store y que estos se
regeneran desde un ledger sembrado.
"""

import json
import shutil
from pathlib import Path

DOCS = Path(__file__).parent.parent / "docs" / "report"


def test_plantilla_importa_datos_generados():
    """escalabilidad.typ toma sus números de los .typ generados, no de constantes."""
    fuente = (DOCS / "escalabilidad.typ").read_text(encoding="utf-8")
    assert '#import "datos.typ": *' in fuente
    assert '#import "escalabilidad_datos.typ": *' in fuente


def test_datos_tip_regenerables_desde_ledger_sembrado(tmp_path: Path):
    """El flujo store → datos .typ funciona con ledger sembrado (T6+T9)."""
    from albertitos.metrics import generar_escalabilidad_datos
    from albertitos.report_data import generar_datos_typ

    base = DOCS.parent.parent / ".sdd" / "pytest-tmp" / "ledger-t11"
    base.mkdir(parents=True, exist_ok=True)
    (base / "decisiones.jsonl").write_text(
        '{"kind": "decision", "invoice_id": "X", "file_id": "x.pdf", "result":'
        ' "PAGAR", "rule_verdicts": [], "config_snapshot": {"rule_set_version": "v4"}}\n',
        encoding="utf-8",
    )
    try:
        d1 = Path(".sdd") / "pytest-tmp" / "datos_t11.typ"
        d2 = Path(".sdd") / "pytest-tmp" / "escal_t11.typ"
        try:
            generar_datos_typ(base, d1)
            generar_escalabilidad_datos(base, d2.parent / "metrics-t11.json", d2)
            assert "v4" in d1.read_text(encoding="utf-8")
            assert "#let archivosPorSegundo" in d2.read_text(encoding="utf-8")
        finally:
            d1.unlink(missing_ok=True)
            (d2.parent / "metrics-t11.json").unlink(missing_ok=True)
            d2.unlink(missing_ok=True)
    finally:
        shutil_rmtree(base)


def test_nuevos_origenes_t10_t12_fluyen_al_typ(tmp_path: Path):
    """T15: corpus-dryrun.json + calibración + drills llegan al .typ con su
    etiqueta, y lo ausente queda como PENDIENTE-MEDICIÓN(T14)."""
    from albertitos.metrics import generar_escalabilidad_datos

    base = Path(".sdd") / "pytest-tmp" / "metrics-t15"
    base.mkdir(parents=True, exist_ok=True)
    (base / "corpus-dryrun.json").write_text(
        json.dumps(
            {
                "kind": "corpus-dryrun",
                "n_files": 500,
                "rung1_files_per_s": 2636.364,
                "rung1_pdf_text": {"archivos_con_texto_usable": 471, "latencia": {"mean_ms": 0.4, "n": 493, "p95_ms": 2.0}},
                "rung2_raster_qr": {"latencia": {"mean_ms": 42.1, "n": 29, "p95_ms": 73.0}},
                "rutas": {"error": 0, "mixed": 0, "raster_no_qr": 29, "rung1_pdf_text": 471, "rung2_qr_only": 0, "timeout": 0},
                "wall_seconds": 3.57,
            }
        ),
        encoding="utf-8",
    )
    (base / "calibracion").mkdir(exist_ok=True)
    (base / "calibracion" / "calibracion-rung3.json").write_text(
        json.dumps(
            {
                "kind": "calibracion-rung3",
                "text_layers_measured": 493,
                "ocr_pages_measured": 29,
                "field_coverage_capas_texto": {"mean": 0.954, "p5": 0.8},
                "field_coverage_ocr": {"mean": 0.483, "p50": 0.4},
                "tabla_umbral_cobertura": {"0.4": {"pct_capas_texto_arriba": 100.0, "pct_ocr_arriba": 72.4}},
                "tabla_umbral_word_conf": {"40.0": {"pct_ocr_arriba": 89.7}},
            }
        ),
        encoding="utf-8",
    )
    (base / "drills.json").write_text(
        json.dumps({"resumen": {"pass": 4, "fail": 0}, "drills": [{"drill": "backoff-429", "pass": True}]}),
        encoding="utf-8",
    )
    destino = Path(".sdd") / "pytest-tmp" / "escal_t15.typ"
    try:
        _, tdest = generar_escalabilidad_datos(
            store_dir=Path(".sdd/pytest-tmp/ledger-t11"),
            json_destino=Path(".sdd/pytest-tmp/metrics-t15.json"),
            typ_destino=destino,
            metrics_dir=base,
        )
        texto = tdest.read_text(encoding="utf-8")
        # T10 citado y medido
        assert '#let dryrunTextoUsable = ("471 / 500 (94.2 %)", "medido")' in texto
        assert '#let dryrunThroughput = ("2636.364", "medido")' in texto
        assert "89.7 % OCR pasa" in texto  # calibración presente
        # T12
        assert '#let drillsResumen = ("4 pass / 0 fail", "medido' in texto
        assert '"backoff-429": "PASS"' in texto
        # placeholders explícitos SOLO para T14
        assert 'PENDIENTE-MEDICIÓN(T14)' in texto
    finally:
        (Path(".sdd") / "pytest-tmp" / "metrics-t15.json").unlink(missing_ok=True)
        destino.unlink(missing_ok=True)
        shutil.rmtree(base)


def test_plantilla_cita_fuentes_de_evidencia():
    """Las secciones citan los ficheros concretos de `.sdd/metrics/`."""
    fuente = (DOCS / "escalabilidad.typ").read_text(encoding="utf-8")
    for citada in ("corpus-dryrun.json", "calibracion-rung3.json", "drills.json"):
        assert citada in fuente, citada
    adr = (DOCS / "albertitos_plan.typ").read_text(encoding="utf-8")
    for citada in (".sdd/metrics/corpus-dryrun.json", ".sdd/metrics/drills.json", "calibracion-rung3.json"):
        assert citada in adr, citada
    # los placeholders T14 entran vía bindings generados, no hardcodeados
    assert "resultadosLote1" in fuente and "exactitudLote1" in fuente
    assert "impactoReprocesado" in fuente


def shutil_rmtree(base: Path) -> None:
    import shutil

    shutil.rmtree(base.parent)
