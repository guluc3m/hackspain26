"""Regenera la cola de revisión real (`.sdd/review-queue/review.jsonl`).

La cola es estado DERIVADO: se reconstruye en segundos desde las caches de
página (sin re-facturar cloud ni re-llamar rung 4 — replay de cache). Útil si
alguien borra la cola (p.ej. un test de otro worker que la trata como scratch)
o tras mover el store.

Idempotente: `enqueue` deduplica por page_sha256; re-ejecutar = no-op.

Uso:
    uv run python tools/regen_review_queue.py \
        [--corpus /home/deploy/hackspain26/caja-de-alberto/facturas] \
        [--store-root .sdd]
"""

from __future__ import annotations

import argparse
import hashlib
import pathlib

from albertitos.extract import ExtractionConfig, ExtractionLadder
from albertitos.store import invoice_uuid

NOMBRE = "resumen de los archivos raster del lote 1"


def main() -> int:
    ap = argparse.ArgumentParser(description=f"Regenera la cola de revisión ({NOMBRE})")
    ap.add_argument("--corpus", default="/home/deploy/hackspain26/caja-de-alberto/facturas")
    ap.add_argument("--store-root", default=".sdd")
    ap.add_argument("--dry-run", action="store_true", help="solo lista los archivos")
    args = ap.parse_args()

    corpus = pathlib.Path(args.corpus)
    raster = sorted(
        f for f in corpus.glob("*.pdf")
        if f.name.startswith("scan_")
        or f.name in ("copia_2026_0518.pdf", "fax_2026_0411.pdf", "reimpresion_0712.pdf")
    )
    print(f"{len(raster)} archivos raster (rung 2+) en el corpus")

    root = pathlib.Path(args.store_root)
    cfg = ExtractionConfig(
        tesseract_bin="/nonexistent/tesseract",  # rung 3: replay del cache o skip
        vlm_base_url="http://127.0.0.1:1",  # rung 4: replay del cache o skip
    )
    lad = ExtractionLadder(
        cfg=cfg, cache_root=root / "cache", review_dir=root / "review-queue"
    )
    q = root / "review-queue" / "review.jsonl"
    for f in raster:
        sha = hashlib.sha256(f.read_bytes()).hexdigest()
        lad.extract_file(f, invoice_id=invoice_uuid(sha), file_id=f.name)
    n = len(q.read_text().splitlines()) if q.is_file() else 0
    print(f"cola regenerada: {n} páginas en {q}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())