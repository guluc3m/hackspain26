"""CLI: run (lote), emit (outcomes desde store), serve (API+UI), reprocess."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import AppConfig
from .pipeline import Pipeline, outcomes_from_store
from .store.db import Store


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="albertitos", description="Sistema de decisión de facturas de Alberto")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="procesa un lote de PDFs")
    p_run.add_argument("--lote", type=Path, required=True, help="directorio con los PDFs")
    p_run.add_argument("--out", type=Path, default=Path("outcomes.jsonl"))

    p_emit = sub.add_parser("emit", help="re-emite outcomes.jsonl desde el store")
    p_emit.add_argument("--out", type=Path, default=Path("outcomes.jsonl"))
    p_emit.add_argument("--run-id", default=None)

    sub.add_parser("serve", help="arranca la API (FastAPI) y la UI")

    p_rep = sub.add_parser("reprocess", help="reprocesa una factura tras override")
    p_rep.add_argument("--invoice-id", required=True)
    p_rep.add_argument("--pdf", type=Path, required=True)

    args = parser.parse_args(argv)
    cfg = AppConfig.load()

    if args.command == "run":
        pipeline = Pipeline(cfg)
        decisions = pipeline.run_lote(args.lote, args.out)
        for d in decisions:
            print(f"{d.file_id}: {d.result.value}")
        return 0

    if args.command == "emit":
        store = Store(cfg.store_path)
        run_id = args.run_id or _latest_run_id(store)
        rows = outcomes_from_store(store, run_id)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"{len(rows)} outcomes -> {args.out}")
        return 0

    if args.command == "serve":
        import uvicorn

        from .api.app import create_app

        uvicorn.run(create_app(), host="127.0.0.1", port=int(__import__("os").environ.get("ALBERTITOS_PORT", "8000")))
        return 0

    if args.command == "reprocess":
        pipeline = Pipeline(cfg)
        d = pipeline.reprocess(args.invoice_id, args.pdf)
        print(f"{d.file_id}: {d.result.value}")
        return 0

    return 1


def _latest_run_id(store: Store) -> str:
    row = store.conn.execute("SELECT id FROM runs ORDER BY started DESC LIMIT 1").fetchone()
    if row is None:
        sys.exit("no hay runs en el store")
    return str(row["id"])


if __name__ == "__main__":
    raise SystemExit(main())
