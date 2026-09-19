"""T33-M1: el PSM de tesseract es configuración, con comportamiento idéntico.

Se prueba con un binario tesseract FALSO (script que registra los args y
devuelve un TSV mínimo válido) — así el test es hermético y verifica el
comando real que el rung 3 ejecuta.
"""

from __future__ import annotations

import os
from pathlib import Path

from albertitos.extract import ExtractionConfig, ExtractionLadder

_FAKETESS_TEMPLATE = (
    "#!/bin/sh\n"
    'case "$*" in *--version*) echo "tesseract 5.5.1"; exit 0;; esac\n'
    'printf "%s\\n" "$@" > "$ARGS_FILE"\n'
    # TSV: cabecera + 5 palabras con confianza alta y campos de factura
    "printf 'level\\tp\\tb\\tp\\tl\\tw\\tx\\ty\\tw\\th\\tconf\\ttext\\n'\n"
    "printf '5\\t1\\t1\\t1\\t1\\t1\\t1\\t1\\t1\\t1\\t90\\tFACTURA\\n'\n"
    "printf '5\\t1\\t1\\t1\\t1\\t2\\t1\\t1\\t1\\t1\\t95\\tFA-8801\\n'\n"
    "printf '5\\t1\\t1\\t1\\t1\\t3\\t1\\t1\\t1\\t1\\t92\\tPO-2026-0096\\n'\n"
    "printf '5\\t1\\t1\\t1\\t1\\t4\\t1\\t1\\t1\\t1\\t88\\t08/01/2026\\n'\n"
    "printf '5\\t1\\t1\\t1\\t1\\t5\\t1\\t1\\t1\\t1\\t90\\t121.00\\n'\n"
)


def _fake_tesseract(tmp_path: Path, args_file: Path) -> str:
    script = tmp_path / "fake-tesseract.sh"
    script.write_text(_FAKETESS_TEMPLATE)
    script.chmod(script.stat().st_mode | 0o755)
    args_file.write_text("")
    os.environ["ARGS_FILE"] = str(args_file)
    return str(script)


def _ladder(tmp_path: Path, psm: int, binario: str) -> ExtractionLadder:
    cfg = ExtractionConfig(
        tesseract_bin=str(binario),
        tesseract_psm=psm,
        vlm_base_url="http://127.0.0.1:1",  # rung 4 down: hermético
    )
    return ExtractionLadder(cfg=cfg, cache_root=tmp_path / "cache")


class TestPsmConfigurable:
    def test_rung3_usa_el_psm_de_config_por_defecto(self, tmp_path):
        args_file = tmp_path / "args6.txt"
        binario = _fake_tesseract(tmp_path, args_file)
        lad = _ladder(tmp_path, psm=6, binario=binario)
        page = lad.extract_file(Path("tests/fixtures/scan_001.pdf"))[0]
        ocr = next(f for f in page.features if f.type == "ocr_text")
        assert not ocr.skipped
        assert ocr.data["text"].startswith("FACTURA FA-8801 PO-2026-0096")
        assert ocr.data["word_conf"] > 60  # el gate con umbrales calibrados pasa
        recibido = args_file.read_text().split()
        assert recibido[recibido.index("--psm") + 1] == "6"

    def test_psm_distinto_se_propaga(self, tmp_path):
        args_file = tmp_path / "args3.txt"
        binario = _fake_tesseract(tmp_path, args_file)
        lad = _ladder(tmp_path, psm=3, binario=binario)
        page = lad.extract_file(Path("tests/fixtures/scan_002.pdf"))[0]
        ocr = next(f for f in page.features if f.type == "ocr_text")
        assert not ocr.skipped
        recibido = args_file.read_text().split()
        assert recibido[recibido.index("--psm") + 1] == "3"
