"""T40F3 — pdfium (pypdfium2) NO es thread-safe: lock global en ladder.py.

Hallazgo (repro real): run.py extrae con 2 workers cuando el rung 4 está
caído — justo la degradación que ejercita el drill — y dos hilos entraban
a la vez en el C de pdfium (PdfDocument / get_page / render / close) ⇒
SIGSEGV del proceso entero, con la suite y el runner 24/7 muertos sin
evidence row. Stack capturado: pypdfium2 document.py get_page ← ladder.py
extract_page (2 hilos) ← run.py _extract (ThreadPoolExecutor).

Fix: _PDFIUM_LOCK alrededor de toda entrada a pdfium en ladder.py. El
raster se serializa; los rungs 3–5 (subproceso/HTTP) siguen en paralelo.

Este test fuerza solape real (4 hilos, 3 rondas, cache fresca por ronda
para que cada página se renderice concurrentemente) y exige que el
resultado sea idéntico al de la corrida serial. Sin el lock, el proceso
crashea con probabilidad alta; con el lock, es determinista.
"""

from __future__ import annotations

import concurrent.futures
from pathlib import Path

from albertitos.extract.config import ExtractionConfig
from albertitos.extract.ladder import ExtractionLadder

REPO = Path(__file__).resolve().parent.parent
FIXTURES = REPO / "tests" / "fixtures"


def _ladder(tmp: Path) -> ExtractionLadder:
    """Hermético: sin tesseract, sin llama-server (rung 4 down)."""
    cfg = ExtractionConfig(
        vlm_base_url="http://127.0.0.1:1",  # nothing listens here
        tesseract_bin="/nonexistent/tesseract",
    )
    return ExtractionLadder(cfg=cfg, cache_root=tmp / "cache",
                            review_dir=tmp / "review")


def _resumen(paginas) -> list[tuple]:
    """Resumen determinista de una extracción (sin timestamps ni bytes)."""
    return [
        (pg.page, pg.page_sha256, pg.final_rung,
         [(ev.stage, ev.outcome) for ev in pg.evidence])
        for pg in paginas
    ]


def test_extraccion_concurrente_igual_a_serial(tmp_path):
    escaneos = sorted((FIXTURES / "scans").glob("scan_*.pdf"))
    texto = sorted((FIXTURES / "facturas").glob("*.pdf"))[:2]
    archivos = escaneos + texto
    assert len(archivos) >= 3, "el test necesita escaneos + facturas de texto"

    # línea base: corrida serial, un ladder, cache propia
    lad_serial = _ladder(tmp_path / "serial")
    serial = [
        _resumen(lad_serial.extract_file(f, invoice_id=f"inv-{i}",
                                         file_id=f.name))
        for i, f in enumerate(archivos)
    ]

    # concurrente: 3 rondas con cache FRESCA (fuerza renders reales) y
    # 4 hilos solapados — el patrón exacto que SEGVeaba sin el lock
    for ronda in range(3):
        lad = _ladder(tmp_path / f"paralelo-{ronda}")
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futs = [
                pool.submit(lad.extract_file, f,
                            invoice_id=f"inv-c{i}-{ronda}", file_id=f.name)
                for i, f in enumerate(archivos)
            ]
            resultados = [_resumen(f.result()) for f in futs]
        assert resultados == serial, f"ronda {ronda}: divergencia"