"""Rasterisation (pypdfium2) and QR detection (cv2) helpers."""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from importlib.metadata import PackageNotFoundError, version

import cv2
import numpy as np
import pypdfium2 as pdfium


def engine_version(engine: str) -> str:
    """Installed version of a dependency, for cache keys and evidence rows."""
    mapping = {"pypdf": "pypdf", "pypdfium2": "pypdfium2", "cv2": "opencv-python-headless"}
    try:
        return version(mapping.get(engine, engine))
    except PackageNotFoundError:  # pragma: no cover - defensive
        return "unknown"


def tesseract_version(bin_path: str | None) -> str:
    """Version reported by the tesseract binary; 'absent' when unavailable."""
    resolved = bin_path or shutil.which("tesseract")
    if not resolved:
        return "absent"
    try:
        proc = subprocess.run(
            [resolved, "--version"], capture_output=True, text=True, timeout=10, check=True
        )
        first = proc.stdout.splitlines()[0] if proc.stdout else ""
        m = re.search(r"(\d+\.\d+\.?\d*)", first)
        return m.group(1) if m else "present"
    except (subprocess.SubprocessError, OSError, IndexError):
        return "present"


def page_sha256(doc_sha256: str, page_index: int) -> str:
    """Stable per-page digest: document content + page position."""
    return hashlib.sha256(f"{doc_sha256}:{page_index}".encode()).hexdigest()


def doc_sha256(pdf_bytes: bytes) -> str:
    return hashlib.sha256(pdf_bytes).hexdigest()


def render_page(page: pdfium.PdfPage, dpi: int) -> np.ndarray:
    """Render one page to a BGR numpy image at the given dpi."""
    bitmap = page.render(scale=dpi / 72, rev_byteorder=True)
    arr = bitmap.to_numpy()
    if arr.ndim == 2:
        return arr
    if arr.shape[2] == 4:
        return cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)
    return arr  # 3-channel BGR already (rev_byteorder)


def encode_png(bgr: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", bgr)
    if not ok:  # pragma: no cover - defensive
        raise RuntimeError("png-encode-failed")
    return buf.tobytes()


def to_gray(bgr: np.ndarray) -> np.ndarray:
    if bgr.ndim == 2:
        return bgr
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)


def detect_qr(gray: np.ndarray) -> tuple[list[str], list[tuple[int, int, int, int]]]:
    """Decode QR payloads; return ([payloads], [bboxes as x, y, w, h])."""
    detector = cv2.QRCodeDetector()
    ok, payloads, points, _ = detector.detectAndDecodeMulti(gray)
    out_payloads: list[str] = []
    boxes: list[tuple[int, int, int, int]] = []
    if ok and points is not None:
        for i, payload in enumerate(payloads):
            pts = points[i].astype(int)
            x0, y0 = int(pts[:, 0].min()), int(pts[:, 1].min())
            x1, y1 = int(pts[:, 0].max()), int(pts[:, 1].max())
            out_payloads.append(payload)
            boxes.append((x0, y0, x1 - x0, y1 - y0))
        return out_payloads, boxes
    # multi-detection fails on some clean single-QR pages — fall back to single
    payload, pts, _ = detector.detectAndDecode(gray)
    if payload:
        if pts is not None and len(pts):
            p = pts.astype(int).reshape(-1, 2)
            x0, y0 = int(p[:, 0].min()), int(p[:, 1].min())
            x1, y1 = int(p[:, 0].max()), int(p[:, 1].max())
            boxes.append((x0, y0, x1 - x0, y1 - y0))
        else:
            boxes.append((0, 0, gray.shape[1], gray.shape[0]))
        return [payload], boxes
    return [], []


def dark_fraction_outside_boxes(
    gray: np.ndarray, boxes: list[tuple[int, int, int, int]], pad: int = 8
) -> float:
    """Fraction of dark pixels that lie OUTSIDE the QR boxes. Near zero means the
    page's only content is the QR(s) (blank background aside)."""
    mask = gray < 200
    total = int(mask.sum())
    if total == 0:
        return 0.0
    outside = mask.copy()
    h, w = gray.shape[:2]
    for x, y, bw, bh in boxes:
        x0, y0 = max(0, x - pad), max(0, y - pad)
        x1, y1 = min(w, x + bw + pad), min(h, y + bh + pad)
        outside[y0:y1, x0:x1] = False
    return int(outside.sum()) / total
