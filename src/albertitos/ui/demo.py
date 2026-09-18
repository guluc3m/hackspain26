"""Datos de prueba deterministas para la UI (fixture del store).

Se usan cuando el ledger aún no tiene datos, para que `uvicorn
albertitos.ui.app:app` muestre las cinco pantallas funcionando desde el
primer minuto (criterio de aceptación de T5). Contenido ficticio, con las
trampas conocidas del corpus como ejemplos.
"""

from __future__ import annotations

import base64
import struct
import zlib

_T = 1_760_000_000.0  # timestamp fijo → salida reproducible


def _png_plano(r: int, g: int, b: int, n: int = 8) -> bytes:
    """PNG mínimo (sin dependencias) para las imágenes de página de prueba."""

    def trozo(tipo: bytes, datos: bytes) -> bytes:
        return (
            struct.pack(">I", len(datos))
            + tipo
            + datos
            + struct.pack(">I", zlib.crc32(tipo + datos) & 0xFFFFFFFF)
        )

    cab = struct.pack(">IIBBBBB", n, n, 8, 2, 0, 0, 0)
    crudo = b"".join(b"\x00" + bytes((r, g, b)) * n for _ in range(n))
    return (
        b"\x89PNG\r\n\x1a\n"
        + trozo(b"IHDR", cab)
        + trozo(b"IDAT", zlib.compress(crudo))
        + trozo(b"IEND", b"")
    )


def _b64(datos: bytes) -> str:
    return base64.b64encode(datos).decode("ascii")


def _ev(invoice, stage, extractor, version, lat, conf, outcome, detail, page=None, cost=None):
    rec = {
        "kind": "evidence",
        "invoice_id": invoice,
        "stage": stage,
        "extractor": extractor,
        "extractor_version": version,
        "config_version": "cfg-2026-06-01",
        "sha256": "0" * 64,
        "latency_ms": lat,
        "confidence": conf,
        "outcome": outcome,
        "detail": detail,
        "timestamp": _T,
    }
    if page is not None:
        rec["page"] = page
    if cost is not None:
        rec["cost_eur"] = cost
    return rec


def _ver(code, outcome, reason, consumed=None):
    return {"code": code, "outcome": outcome, "reason": reason, "consumed": consumed or {}}


def _dec(invoice, file_id, result, verdicts):
    return {
        "kind": "decision",
        "invoice_id": invoice,
        "file_id": file_id,
        "result": result,
        "rule_verdicts": verdicts,
        "config_snapshot": {
            "rule_set_version": "v4",
            "thresholds": {
                "TOTALS_MUST_MATCH": 0.8,
                "NIF_IN_MASTER": 0.9,
                "IBAN_MATCHES_MASTER": 0.9,
                "IVA_CONSISTENT": 0.8,
                "ORDER_PENDING": 0.7,
            },
        },
        "timestamp": _T + 5,
    }


def demo_records() -> list[dict]:
    """Registros JSONL de ejemplo (mismo formato que escribe el pipeline)."""
    img_qr = _b64(_png_plano(60, 60, 60))
    img_borrosa = _b64(_png_plano(200, 170, 120))
    registros: list[dict] = []

    # INV-0001 — PAGAR, extracción por capa de texto.
    registros += [
        _ev("INV-0001", "extract", "pypdf", "5.6.0", 120, 0.97, "ok", "capa de texto utilizable", page=1),
        _ev("INV-0001", "render", "pypdfium2", "4.30", 45, None, "ok", "1 página renderizada", page=1),
        _ev("INV-0001", "parse", "regex", "0.3.0", 8, 0.95, "ok", "6 campos, 1 candidata cada uno"),
        _ev(
            "INV-0001",
            "decide",
            "rule-engine",
            "v4",
            2,
            None,
            "ok",
            "6 reglas evaluadas",
            cost=0.0,
        ),
    ]
    registros.append(
        _dec(
            "INV-0001",
            "2026-05-28_P005.pdf",
            "PAGAR",
            [
                _ver("TOTALS_MUST_MATCH", "PASS", "121.00 € = 100 + 21 IVA", {"_confianza": 0.97, "_umbral": 0.8}),
                _ver("NIF_IN_MASTER", "PASS", "B46102331 en maestro de proveedores", {"_confianza": 0.95, "_umbral": 0.9}),
                _ver("IVA_CONSISTENT", "PASS", "21 % sobre base 100,00 €", {"_confianza": 0.96, "_umbral": 0.8}),
                _ver("DATE_VALID_NOT_FUTURE", "PASS", "fecha 2026-05-28, no futura", {"_confianza": 0.99, "_umbral": 0.8}),
                _ver("ORDER_PENDING", "PASS", "pedido P005 pendiente de factura", {"_confianza": 0.92, "_umbral": 0.7}),
                _ver("NO_DOUBLE_PAYMENT", "PASS", "sin pago previo registrado", {"_confianza": 1.0, "_umbral": 0.9}),
                _ver("IBAN_MATCHES_MASTER", "PASS", "IBAN coincide con el maestro", {"_confianza": 0.99, "_umbral": 0.9}),
            ],
        )
    )

    # INV-0002 — NO_PAGAR: duplicado de FA-8801 (trampa del corpus).
    registros += [
        _ev("INV-0002", "extract", "pypdf", "5.6.0", 118, 0.96, "ok", "capa de texto utilizable", page=1),
        _ev("INV-0002", "parse", "regex", "0.3.0", 9, 0.94, "ok", "6 campos"),
        _ev("INV-0002", "decide", "rule-engine", "v4", 2, None, "ok", "6 reglas evaluadas", cost=0.0),
    ]
    registros.append(
        _dec(
            "INV-0002",
            "factura_8801.pdf",
            "NO_PAGAR",
            [
                _ver("TOTALS_MUST_MATCH", "PASS", "totales cuadran", {"_confianza": 0.96, "_umbral": 0.8}),
                _ver("NIF_IN_MASTER", "PASS", "B46102331 en maestro", {"_confianza": 0.95, "_umbral": 0.9}),
                _ver("NO_DOUBLE_PAYMENT", "FAIL", "FA-8801 duplicada de 2026-05-28_P005.pdf", {"_confianza": 0.98, "_umbral": 0.9}),
            ],
        )
    )

    # INV-0003 — NO_PAGAR: proveedor fantasma con IBAN compartido (trampa).
    registros += [
        _ev("INV-0003", "extract", "pypdf", "5.6.0", 110, 0.93, "ok", "capa de texto utilizable", page=1),
        _ev("INV-0003", "parse", "regex", "0.3.0", 11, 0.9, "ok", "6 campos"),
        _ev("INV-0003", "decide", "rule-engine", "v4", 2, None, "ok", "6 reglas evaluadas", cost=0.0),
    ]
    registros.append(
        _dec(
            "INV-0003",
            "proveedor_fantasma_a.pdf",
            "NO_PAGAR",
            [
                _ver("NIF_IN_MASTER", "FAIL", "NIF B99999999 no está en el maestro", {"_confianza": 0.93, "_umbral": 0.9}),
                _ver("IBAN_MATCHES_MASTER", "FAIL", "IBAN ES66…9877 compartido por 3 proveedores distintos", {"_confianza": 0.97, "_umbral": 0.9}),
                _ver("ORDER_BELONGS_TO_SUPPLIER", "FAIL", "pedido P005 pertenece a otro proveedor", {"_confianza": 0.91, "_umbral": 0.8}),
            ],
        )
    )

    # INV-0004 — ESCALAR: escaneo ilegible, OCR con confianza baja.
    registros += [
        _ev("INV-0004", "extract", "pypdf", "5.6.0", 95, None, "skipped:sin_capa_de_texto", "0 caracteres extraídos", page=1),
        _ev("INV-0004", "render", "pypdfium2", "4.30", 50, None, "ok", "1 página renderizada", page=1),
        _ev("INV-0004", "extract", "tesseract", "5.3.4", 1900, 0.51, "ok", "confianza baja de palabras", page=1),
        _ev("INV-0004", "extract", "vlm", "paddleocr-vl-q8", 4200, 0.58, "ok", "lectura local dudosa", page=1, cost=0.0),
        _ev("INV-0004", "decide", "rule-engine", "v4", 2, None, "ok", "2 reglas UNKNOWN", cost=0.0),
    ]
    registros.append(
        _dec(
            "INV-0004",
            "escan_ilegible_07.pdf",
            "ESCALAR",
            [
                _ver("TOTALS_MUST_MATCH", "UNKNOWN", "confianza de lectura 0.51 < umbral 0.8", {"_confianza": 0.51, "_umbral": 0.8}),
                _ver("NIF_IN_MASTER", "UNKNOWN", "NIF ilegible", {"_confianza": 0.49, "_umbral": 0.9}),
            ],
        )
    )
    registros.append(
        {
            "kind": "fields",
            "invoice_id": "INV-0004",
            "file_id": "escan_ilegible_07.pdf",
            "fields": {
                "total": [
                    {"extractor": "tesseract", "value": "1 210,00 €", "confidence": 0.51},
                    {"extractor": "vlm", "value": "1210,00 €", "confidence": 0.58},
                ],
                "nif": [{"extractor": "tesseract", "value": "B4?10233?", "confidence": 0.49}],
            },
            "page_images": {"1": img_borrosa},
        }
    )

    # INV-0005 — ESCALAR: desacuerdo entre extractores sobre el total.
    registros += [
        _ev("INV-0005", "extract", "pypdf", "5.6.0", 125, 0.9, "ok", "capa de texto utilizable", page=1),
        _ev("INV-0005", "extract", "tesseract", "5.3.4", 2100, 0.62, "ok", "tabla mal alineada", page=1),
        _ev("INV-0005", "decide", "rule-engine", "v4", 3, None, "ok", "1 regla UNKNOWN", cost=0.0),
    ]
    registros.append(
        _dec(
            "INV-0005",
            "factura_outlier_44.pdf",
            "ESCALAR",
            [
                _ver("TOTALS_MUST_MATCH", "UNKNOWN", "las dos lecturas del total no cuadran con el desglose", {"_confianza": 0.62, "_umbral": 0.8}),
                _ver("IVA_CONSISTENT", "UNKNOWN", "IVA declarado no coincide con ninguna lectura", {"_confianza": 0.55, "_umbral": 0.8}),
            ],
        )
    )
    registros.append(
        {
            "kind": "fields",
            "invoice_id": "INV-0005",
            "file_id": "factura_outlier_44.pdf",
            "fields": {
                "total": [
                    {"extractor": "pypdf", "value": 121.0, "confidence": 0.9},
                    {"extractor": "tesseract", "value": 1210.0, "confidence": 0.62},
                ],
                "iva_amount": [
                    {"extractor": "pypdf", "value": 25.41, "confidence": 0.88},
                    {"extractor": "tesseract", "value": 254.1, "confidence": 0.55},
                ],
            },
            "page_images": {"1": img_qr},
        }
    )

    # INV-0006 — PAGAR tras QR.
    registros += [
        _ev("INV-0006", "extract", "pypdf", "5.6.0", 90, None, "skipped:sin_capa_de_texto", "página solo con QR", page=1),
        _ev("INV-0006", "extract", "zxing", "2.3.0", 140, 0.99, "ok", "payload QR decodificado", page=1),
        _ev("INV-0006", "decide", "rule-engine", "v4", 2, None, "ok", "5 reglas evaluadas", cost=0.0),
    ]
    registros.append(
        _dec(
            "INV-0006",
            "2026-06-02_P012.pdf",
            "PAGAR",
            [
                _ver("TOTALS_MUST_MATCH", "PASS", "datos del QR estándar", {"_confianza": 0.99, "_umbral": 0.8}),
                _ver("NIF_IN_MASTER", "PASS", "B46102331 en maestro", {"_confianza": 0.97, "_umbral": 0.9}),
                _ver("ORDER_PENDING", "PASS", "pedido P012 pendiente", {"_confianza": 0.94, "_umbral": 0.7}),
                _ver("NO_DOUBLE_PAYMENT", "PASS", "sin pago previo", {"_confianza": 0.98, "_umbral": 0.9}),
                _ver("DATE_VALID_NOT_FUTURE", "PASS", "fecha 2026-06-02", {"_confianza": 0.99, "_umbral": 0.8}),
            ],
        )
    )

    # Salud: fallo de proveedor cloud con reintentos.
    registros += [
        _ev("INV-0004", "extract", "cloud_vlm", "gemini-25b", 800, None, "error", "HTTP 429 — cuota agotada", page=1),
        _ev("INV-0004", "extract", "cloud_vlm", "gemini-25b", 820, None, "error", "reintento 1 — HTTP 429", page=1),
        _ev("INV-0004", "extract", "cloud_vlm", "gemini-25b", 850, None, "error", "reintento 2 — HTTP 429", page=1),
        _ev("INV-0005", "extract", "tesseract", "5.3.4", 60, None, "skipped:tesseract_no_instalado", "binario ausente en este nodo", page=2),
    ]
    return registros
