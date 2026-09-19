"""Append-only scan evidence; active only inside an ingest invocation."""

from __future__ import annotations

import contextlib
import contextvars
import mimetypes
import shutil
import time
import uuid
from dataclasses import asdict
from pathlib import Path

from .pouch import INLINE_LIMIT, PouchStore, canonical, file_key

_active: contextvars.ContextVar[ScanTrace | None] = contextvars.ContextVar(
    "scan_trace", default=None
)


class ScanTrace:
    def __init__(
        self,
        store: PouchStore,
        source: Path,
        sha: str,
        invoice_id: str,
        scan_id: str | None = None,
        resume: bool = False,
    ) -> None:
        self.store = store
        self.scan_id = scan_id or str(uuid.uuid4())
        self.resume = resume
        self.identity = {
            "scan_id": self.scan_id,
            "file_key": file_key(source.name, sha),
            "file_id": source.name,
            "invoice_id": invoice_id,
        }
        self.source = source
        self.sha = sha
        self.features: dict[int, list[str]] = {}
        self.work = store.root / "scans" / self.scan_id

    @contextlib.contextmanager
    def active(self):
        token = _active.set(self)
        try:
            yield self
        finally:
            _active.reset(token)

    def begin(
        self, config_version: str, extraction_config_version: str, master_sha256: str
    ) -> Path:
        from filemaid.extract.cache import sha256_file

        self.store.put(
            {
                "_id": f"file:{self.identity['file_key']}",
                "kind": "file",
                **{k: v for k, v in self.identity.items() if k != "scan_id"},
                "sha256": self.sha,
            }
        )
        self.record(
            "scan",
            f"scan:{self.identity['file_key']}:{self.scan_id}",
            {
                "source_path": str(self.source.resolve()),
                "sha256": self.sha,
                "config_version": config_version,
                "extraction_config_version": extraction_config_version,
                "master_sha256": master_sha256,
            },
        )
        self.work.mkdir(parents=True, exist_ok=True)
        copy = self.work / self.source.name
        shutil.copyfile(self.source, copy)
        if sha256_file(copy) != self.sha:
            raise RuntimeError("Source changed during ingest")
        existing = self.store.list(f"artifact:{self.scan_id}:")
        if not (self.resume and any(a.get("stage") == "input" for a in existing)):
            self.artifact(
                "input",
                self.source.name,
                copy,
                mimetypes.guess_type(copy.name)[0] or "application/octet-stream",
            )
        return copy

    def record(self, kind: str, doc_id: str, payload: dict) -> str:
        # A resumed scan (review transaction retry) reuses the documents already
        # written by the interrupted attempt instead of colliding on them.
        if self.resume and self.store.get(doc_id) is not None:
            return doc_id
        if len(canonical(payload)) > INLINE_LIMIT:
            ref = self.artifact(kind, f"{kind}.json", canonical(payload), "application/json")
            routing = {
                k: payload[k]
                for k in ("type", "stage", "page", "run_id", "fields_id")
                if k in payload
            }
            if kind == "decision":
                routing["result"] = payload["decision"]["result"]
            payload = {"payload_ref": ref, "encoding": "json", **routing}
        return self.store.put(
            {
                **self.identity,
                "_id": doc_id,
                "kind": kind,
                "timestamp": time.time(),
                **payload,
            }
        )

    def artifact(self, stage: str, name: str, source, media_type: str) -> str:
        return self.store.artifact(self.identity, stage, name, source, media_type)

    def event(self, event_type: str, payload: dict) -> None:
        self.record(
            "event",
            f"event:{self.scan_id}:{uuid.uuid4()}",
            {"type": event_type, "payload": payload},
        )

    def rung(self, page: int, stage: str, features: list, pages_dir: Path | None) -> None:
        refs = self.features.setdefault(page, [])
        for feat in features:
            value = asdict(feat)
            if isinstance(value["data"], bytes):
                value["data"] = {
                    "artifact_id": self.artifact(
                        stage, "data.bin", value["data"], "application/octet-stream"
                    )
                }
            if (
                feat.type == "page_image"
                and feat.extraction_method == "pypdfium2"
                and pages_dir is not None
            ):
                image = pages_dir / f"p{page}.png"
                if image.exists():
                    from filemaid.extract.cache import sha256_file

                    if feat.sha256 and sha256_file(image) != feat.sha256:
                        raise RuntimeError("Page image does not match extraction evidence")
                    self.artifact(stage, image.name, image, "image/png")
            ref = self.record(
                "feature",
                f"feature:{self.scan_id}:{page}:{stage}:{len(refs)}",
                {
                    "stage": stage,
                    "page": page,
                    "feature": value,
                },
            )
            refs.append(ref)
            self.event(
                "feature",
                {
                    "document_id": ref,
                    "stage": stage,
                    "page": page,
                    "outcome": feat.extraction_method,
                    "latency_ms": feat.latency_ms,
                },
            )

    def pages(self, pages: list, pages_dir: Path) -> None:
        for page in pages:
            if page.page not in self.features:
                for feat in page.features:
                    self.rung(page.page, feat.extraction_method, [feat], pages_dir)
                self.page(page)

    def page(self, page) -> None:
        self.record(
            "page",
            f"page:{self.scan_id}:{page.page}",
            {
                "page": page.page,
                "content": page.content,
                "stopped_at": page.stopped_at,
                "features": self.features.get(page.page, []),
            },
        )

    def fields(self, fields: list, parser_ms: int) -> None:
        ref = self.record(
            "fields",
            f"fields:{self.scan_id}",
            {
                "fields": [asdict(f) for f in fields],
                "parser_ms": parser_ms,
            },
        )
        self.event("fields", {"document_id": ref, "parser_ms": parser_ms})

    def decision(self, decision, run_id: str, overrides_applied: list | None = None) -> None:
        payload = {
            "decision": asdict(decision),
            "run_id": run_id,
            "fields_id": f"fields:{self.scan_id}",
        }
        if overrides_applied:
            payload["overrides_applied"] = overrides_applied
        self.record("decision", f"decision:{self.scan_id}", payload)


def current_trace() -> ScanTrace | None:
    return _active.get()


def capture_artifact(stage: str, name: str, data, media_type: str) -> None:
    if trace := current_trace():
        trace.artifact(stage, name, data, media_type)


def capture_response(stage: str, response) -> None:
    if trace := current_trace():
        trace.artifact(stage, "response.json", response.content, "application/json")
