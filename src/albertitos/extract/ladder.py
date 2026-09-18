"""Orchestrator: runs the ladder per PAGE, with cache and evidence.

The ladder is skippable by construction: any missing dependency yields a
`skipped:<reason>` feature and the batch keeps moving (AGENTS.md §3). Every
rung records an evidence row; nothing returns bare strings.
"""

from __future__ import annotations

import dataclasses
import io
from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium
from pypdf import PdfReader

from albertitos.extract.cache import PageCache
from albertitos.extract.cloud import prompt_sha256, run_cloud_vlm
from albertitos.extract.config import ExtractionConfig
from albertitos.extract.evidence import EvidenceLedger
from albertitos.extract.raster import (
    doc_sha256,
    encode_png,
    engine_version,
    page_sha256,
    render_page,
)
from albertitos.extract.review import ReviewQueue
from albertitos.extract.rungs import (
    RungContext,
    run_raster_qr,
    run_tesseract,
    run_text_layer,
    run_vlm,
    tesseract_version,
)
from albertitos.types import EvidenceRow, ExtractionFeature


@dataclass
class PageExtraction:
    """Everything one page produced — features plus its evidence chain."""

    page: int  # 1-based
    page_sha256: str
    features: list[ExtractionFeature] = dataclasses.field(default_factory=list)
    evidence: list[EvidenceRow] = dataclasses.field(default_factory=list)
    # rung1_pdf_text | rung2_qr | rung3_ocr | rung4_vlm | rung5_cloud | unresolved
    final_rung: str = "unresolved"
    qr_only: bool = False
    escalated: bool = False  # entered the human review queue (never blocks)


class ExtractionLadder:
    """Runs rungs 1–5 per page. Skippable, cached, evidence-logged.

    Rung 5 (cloud VLM) is the ESCALATION path: it fires only when tesseract
    AND the local VLM left the page unresolved. Its reading is one more
    candidate — never an automatic answer — and an escalated page enters the
    human review queue without ever blocking the batch (AGENTS.md §3, §7).
    """

    def __init__(
        self,
        cfg: ExtractionConfig | None = None,
        cache_root: Path | str | None = None,
        evidence_path: Path | str | None = None,
        cloud: object | None = None,
        http_transport: object | None = None,
        review_dir: Path | str | None = None,
    ):
        self.cfg = cfg or ExtractionConfig()
        self.cache = PageCache(Path(cache_root or ".sdd/cache"))
        self.ledger = EvidenceLedger(Path(evidence_path) if evidence_path else None)
        self.cloud = cloud
        self.http_transport = http_transport
        review_root = Path(review_dir) if review_dir else self.cache.root.parent / "review-queue"
        self.review = ReviewQueue(review_root)

    # ------------------------------------------------------------- public API

    def extract_file(
        self,
        pdf_path: str | Path,
        invoice_id: str | None = None,
        file_id: str | None = None,
    ) -> list[PageExtraction]:
        """Run the ladder over every page of one file. Per page, not per file:
        a PDF may mix pages of different kinds."""
        pdf_path = Path(pdf_path)
        invoice_id = invoice_id or pdf_path.name
        file_id = file_id or pdf_path.name
        pdf_bytes = pdf_path.read_bytes()
        try:
            n_pages = len(PdfReader(io.BytesIO(pdf_bytes)).pages)
        except Exception as exc:  # noqa: BLE001 - damaged file degrades, never halts
            self.ledger.append(
                EvidenceRow(
                    invoice_id=invoice_id,
                    stage="extract:open",
                    extractor="pypdf",
                    extractor_version=engine_version("pypdf"),
                    config_version=self.cfg.config_version,
                    sha256=doc_sha256(pdf_bytes),
                    latency_ms=0,
                    confidence=None,
                    outcome="error",
                    detail=f"unreadable-pdf:{exc}",
                )
            )
            return []
        return [self.extract_page(pdf_bytes, i, invoice_id, file_id=file_id) for i in range(n_pages)]

    def extract_page(
        self, pdf_bytes: bytes, page_index: int, invoice_id: str, file_id: str | None = None
    ) -> PageExtraction:
        dsha = doc_sha256(pdf_bytes)
        psha = page_sha256(dsha, page_index)
        page_no = page_index + 1
        file_id = file_id or invoice_id
        out = PageExtraction(page=page_no, page_sha256=psha)

        pdfium_doc = pdfium.PdfDocument(pdf_bytes)
        try:
            # ---- rung 1: text layer (cheap + deterministic, no cache needed)
            pdf_text = self._extract_text(pdf_bytes, page_index)
            ctx1 = self._ctx(invoice_id, page_no, psha, pdf_text, None, None, out.evidence)
            r1 = run_text_layer(ctx1)
            out.features.extend(r1.features)
            if r1.stop:
                out.final_rung = "rung1_pdf_text"
                return self._finish(out)

            # the rendered PNG feeds rungs 2–4 and the review UI; cached on disk
            png_bytes = self._ensure_png(page_no and pdfium_doc[page_index], psha)

            def ctx2() -> RungContext:
                bgr = render_page(pdfium_doc[page_index], self.cfg.dpi)
                return self._ctx(invoice_id, page_no, psha, pdf_text, bgr, png_bytes, out.evidence)

            def ctx34() -> RungContext:
                return self._ctx(invoice_id, page_no, psha, pdf_text, None, png_bytes, out.evidence)

            # ---- rung 2: raster + QR (cached)
            r2 = self._rung_cached(
                engine="raster_qr",
                ev_version=engine_version("pypdfium2"),
                psha=psha,
                invoice_id=invoice_id,
                rung_fn=run_raster_qr,
                ctx_factory=ctx2,
                out=out,
            )
            out.features.extend(r2.features)
            out.qr_only = r2.stop
            if r2.stop:
                out.final_rung = "rung2_qr"
                return self._finish(out)

            # ---- rung 3: tesseract (skippable)
            ev_tess = tesseract_version(self.cfg.tesseract_bin)
            r3 = self._rung_cached(
                engine="tesseract",
                ev_version=ev_tess,
                psha=psha,
                invoice_id=invoice_id,
                rung_fn=run_tesseract,
                ctx_factory=ctx34,
                out=out,
            )
            out.features.extend(r3.features)
            if r3.stop:
                out.final_rung = "rung3_ocr"
                return self._finish(out)

            # ---- rung 4: local VLM (skippable)
            r4 = self._rung_cached(
                engine="vlm",
                ev_version=self.cfg.vlm_model,
                psha=psha,
                invoice_id=invoice_id,
                rung_fn=run_vlm,
                ctx_factory=ctx34,
                out=out,
            )
            out.features.extend(r4.features)
            if r4.stop:
                out.final_rung = "rung4_vlm"
                return self._finish(out)

            # ---- rung 5: cloud VLM escalation (cached; reading = candidate only)
            r5 = self._rung_cached(
                engine="cloud_vlm",
                ev_version=self.cloud.model if self.cloud is not None else "unconfigured",
                psha=psha,
                invoice_id=invoice_id,
                rung_fn=run_cloud_vlm,
                ctx_factory=ctx34,
                out=out,
            )
            out.features.extend(r5.features)
            cloud_ok = any(
                f.type == "cloud_vlm_text" and not f.skipped for f in r5.features
            )
            cloud_model = self.cloud.model if self.cloud is not None else ""
            motivo = r5.detail or "escalated-after-rung4"
            if cloud_ok:
                out.final_rung = "rung5_cloud"
            out.escalated = True
            self.review.enqueue(
                invoice_id=invoice_id,
                file_id=file_id,
                page=page_no,
                page_sha256=psha,
                motivo=motivo,
                features=out.features,
                cloud_ok=cloud_ok,
                cloud_model=cloud_model,
                config_version=self.cfg.config_version,
                png_bytes=png_bytes,
                extra_provenance={"prompt_sha256": prompt_sha256()},
            )
            return self._finish(out)
        finally:
            pdfium_doc.close()

    # ------------------------------------------------------------- internals

    def _finish(self, out: PageExtraction) -> PageExtraction:
        for row in out.evidence:
            self.ledger.append(row)
        return out

    def _ctx(
        self,
        invoice_id: str,
        page_no: int,
        psha: str,
        pdf_text: str,
        render_bgr,
        render_png: bytes | None,
        evidence: list[EvidenceRow],
    ) -> RungContext:
        return RungContext(
            invoice_id=invoice_id,
            page=page_no,
            page_sha=psha,
            cfg=self.cfg,
            pdf_text=pdf_text,
            render_bgr=render_bgr,
            render_png=render_png,
            render_png_path=self.cache.root / "images" / f"{psha}.png",
            cloud=self.cloud,
            http_transport=self.http_transport,
            evidence=evidence,
        )

    def _ensure_png(self, page: pdfium.PdfPage, psha: str) -> bytes:
        """Rendered PNG for this page, from the image cache when possible."""
        png_path = self.cache.root / "images" / f"{psha}.png"
        if png_path.is_file():
            return png_path.read_bytes()
        png = encode_png(render_page(page, self.cfg.dpi))
        png_path.parent.mkdir(parents=True, exist_ok=True)
        png_path.write_bytes(png)
        return png

    def _rung_cached(self, *, engine, ev_version, psha, invoice_id, rung_fn, ctx_factory, out):
        """Run one rung through the page cache (key: page/engine/version/config)."""
        cached = self.cache.get(psha, engine, ev_version, self.cfg.config_version)
        if cached is not None:
            out.evidence.append(
                EvidenceRow(
                    invoice_id=invoice_id,
                    stage=f"extract:{engine}",
                    extractor=engine,
                    extractor_version=ev_version,
                    config_version=self.cfg.config_version,
                    sha256=psha,
                    latency_ms=0,
                    confidence=None,
                    outcome="cache_hit",
                    detail="replayed from cache",
                )
            )
            features = [_feature_from_json(f) for f in cached.get("features", [])]
            return RungResult(features=features, stop=bool(cached.get("stop")), detail="cache")

        ctx = ctx_factory()
        result = rung_fn(ctx)
        payload = {
            "features": [_feature_to_json(f, psha, self.cache.root) for f in result.features],
            "stop": result.stop,
            "detail": result.detail,
        }
        self.cache.put(psha, engine, ev_version, self.cfg.config_version, payload)
        return result

    def _extract_text(self, pdf_bytes: bytes, page_index: int) -> str:
        try:
            reader = PdfReader(io.BytesIO(pdf_bytes))
            return reader.pages[page_index].extract_text() or ""
        except Exception:  # noqa: BLE001 - empty text falls through the plausibility gate
            return ""


class RungResult:
    """Outcome of one rung: features + stop decision (mirrors RungOutcome)."""

    def __init__(self, features: list, stop: bool, detail: str = ""):
        self.features = features
        self.stop = stop
        self.detail = detail


def _feature_to_json(feat: ExtractionFeature, page_sha: str, cache_root: Path) -> dict:
    d = {
        "type": feat.type,
        "extraction_method": feat.extraction_method,
        "timestamp": feat.timestamp,
        "page": feat.page,
        "sha256": feat.sha256,
        "latency_ms": feat.latency_ms,
        "skipped": feat.skipped,
    }
    if isinstance(feat.data, bytes):
        # page PNGs live next to the cache entries; they feed rungs 3–5 and review
        img_dir = cache_root / "images"
        img_dir.mkdir(parents=True, exist_ok=True)
        img_path = img_dir / f"{page_sha}.png"
        if not img_path.exists():
            img_path.write_bytes(feat.data)
        d["data"] = {"png_file": str(img_path)}
    else:
        d["data"] = feat.data
    return d


def _feature_from_json(d: dict) -> ExtractionFeature:
    data = d["data"]
    if isinstance(data, dict) and "png_file" in data:
        p = Path(data["png_file"])
        data = p.read_bytes() if p.is_file() else b""
    return ExtractionFeature(
        type=d["type"],
        extraction_method=d["extraction_method"],
        timestamp=d["timestamp"],
        data=data,
        page=d["page"],
        sha256=d["sha256"],
        latency_ms=d["latency_ms"],
        skipped=d["skipped"],
    )
