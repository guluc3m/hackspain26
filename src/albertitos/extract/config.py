"""Configuration for the extraction ladder. Thresholds are config, not code."""

from __future__ import annotations

from dataclasses import dataclass

CONFIG_VERSION = "extract-v1"


@dataclass(frozen=True)
class ExtractionConfig:
    """Every threshold of the ladder lives here; bump `config_version` on change
    so page caches are invalidated together (key: page_sha/engine/version/config)."""

    config_version: str = CONFIG_VERSION

    # rung 1 — pdf text layer (pypdf)
    min_text_chars: int = 20
    max_cid_per_kchar: float = 1.0  # "(cid:N)" occurrences per 1000 chars
    max_replacement_ratio: float = 0.02  # U+FFFD / control chars per char
    min_dict_ratio: float = 0.6  # plausible alphabetic tokens / total tokens

    # rung 2 — raster + QR (pypdfium2 + cv2)
    dpi: int = 150
    qr_only_max_outside_dark_fraction: float = 0.02

    # rung 3 — tesseract OCR
    tesseract_bin: str | None = None  # None = shutil.which("tesseract")
    tesseract_min_word_conf: float = 60.0
    tesseract_min_field_coverage: float = 0.5

    # rung 4 — local VLM via llama-server (OpenAI-compatible)
    vlm_base_url: str = "http://127.0.0.1:8080"
    vlm_model: str = "paddleocr-vl"
    vlm_timeout_s: float = 60.0
    vlm_min_field_coverage: float = 0.5

    # fields the OCR/VLM coverage term looks for (ticket T1 rungs 3–4)
    expected_fields: tuple[str, ...] = ("nif", "iban", "fecha", "total", "pedido")
