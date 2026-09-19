"""CLI: run (lote), emit (outcomes desde store), serve (API+UI), server (FastAPI), reprocess."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from .config import AppConfig
from .pipeline import Pipeline, outcomes_from_store
from .rules.report import write_report
from .runtime import RuntimeSettings
from .store.pouch import PouchStore
from .store.queries import archive_output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="filemaid", description="Sistema de decisión de facturas de Alberto"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="procesa un lote de PDFs")
    p_run.add_argument("--lote", type=Path, required=True, help="directorio con los PDFs")
    p_run.add_argument("--out", type=Path, default=Path("outcomes.jsonl"))
    p_run.add_argument(
        "--no-report", action="store_true", help="no genera el informe HTML tras el lote"
    )
    p_run.add_argument(
        "--report-dir",
        type=Path,
        default=Path("rules"),
        help="directorio del informe HTML (reglas + breadcrumbs)",
    )

    p_emit = sub.add_parser("emit", help="re-emite outcomes.jsonl desde el store")
    p_emit.add_argument("--out", type=Path, default=Path("outcomes.jsonl"))
    p_emit.add_argument("--run-id", default=None)

    p_report = sub.add_parser(
        "report", help="informe HTML de un run: reglas y breadcrumbs por factura"
    )
    p_report.add_argument("--run-id", default=None, help="por defecto, el último run")
    p_report.add_argument(
        "--out", type=Path, default=Path("rules"), help="directorio de salida del informe"
    )

    sub.add_parser("serve", help="arranca la API (FastAPI) y la UI")

    p_server = sub.add_parser("server", help="arranca el servidor de sincronización y VLM")
    p_server.add_argument("--host", default="127.0.0.1", help="host del servidor")
    p_server.add_argument("--port", type=int, default=8001, help="puerto del servidor")

    p_rep = sub.add_parser("reprocess", help="reprocesa una factura tras override")
    p_rep.add_argument("--invoice-id", required=True)
    p_rep.add_argument("--pdf", type=Path, required=True)

    p_clean = sub.add_parser(
        "clean", help="borra los espacios de trabajo temporales (páginas rasterizadas)"
    )
    p_clean.add_argument("--pages", action="store_true", help="borra las páginas rasterizadas")
    p_clean.add_argument("--yes", "-y", action="store_true", help="no pide confirmación")

    args = parser.parse_args(argv)
    cfg = AppConfig.load()

    if args.command == "run":
        pipeline = Pipeline(cfg)
        decisions = pipeline.run_lote(args.lote, args.out)
        counts: dict[str, int] = {}
        total_time_ms = 0
        extraction_time_ms = 0
        parser_time_ms = 0
        evaluation_time_ms = 0
        for d in decisions:
            counts[d.result.value] = counts.get(d.result.value, 0) + 1
            total_time_ms += d.total_ms
            extraction_time_ms += d.extraction_ms
            parser_time_ms += d.parser_ms
            evaluation_time_ms += d.evaluation_ms
        for result in ("PAGAR", "NO_PAGAR", "ESCALAR"):
            print(f"{result}: {counts.get(result, 0)}")
        n_invoices = len(decisions)
        avg_time_ms = total_time_ms / n_invoices if n_invoices > 0 else 0.0
        print(
            f"tiempo: {total_time_ms} ms total · {avg_time_ms:.1f} ms/factura "
            f"(extracción: {extraction_time_ms} ms · parser: {parser_time_ms} ms · reglas: {evaluation_time_ms} ms)"
        )
        if not args.no_report and decisions:
            out = write_report(pipeline.store, cfg, pipeline.rule_config.version, args.report_dir)
            print(f"informe: {out / 'index.html'}")
            if cfg.runtime_settings()["mode"] == "server":
                RuntimeSettings(cfg).sync()
        return 0

    if args.command == "report":
        store = PouchStore(cfg.root)
        run_id = args.run_id or _latest_run_id(store)
        out = write_report(store, cfg, run_id, args.out)
        decisions_in_run = [
            d for d in store.list("decision:") if store.hydrate(d).get("run_id") == run_id
        ]
        print(f"{len(decisions_in_run)} facturas -> {out / 'index.html'}")
        if cfg.runtime_settings()["mode"] == "server":
            RuntimeSettings(cfg).sync()
        return 0

    if args.command == "emit":
        store = PouchStore(cfg.root)
        run_id = args.run_id or _latest_run_id(store)
        rows = outcomes_from_store(store, run_id)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        for raw in store.list("decision:"):
            d = store.hydrate(raw)
            if d.get("run_id") == run_id and d.get("scan_id"):
                archive_output(cfg.root, d["scan_id"], args.out, "application/x-ndjson")
        print(f"{len(rows)} outcomes -> {args.out}")
        if cfg.runtime_settings()["mode"] == "server":
            RuntimeSettings(cfg).sync()
        return 0

    if args.command == "serve":
        import uvicorn

        from .api.app import create_app

        uvicorn.run(
            create_app(),
            host="127.0.0.1",
            port=int(os.environ.get("FILEMAID_PORT", "8000")),
        )
        return 0

    if args.command == "server":
        import uvicorn

        from .server import create_server

        is_loopback = args.host in {"127.0.0.1", "localhost", "::1"}
        if not is_loopback and not os.environ.get("FILEMAID_SERVER_TOKEN"):
            sys.exit("Error: FILEMAID_SERVER_TOKEN es requerido cuando --host no es loopback")

        app = create_server(cfg)
        uvicorn.run(app, host=args.host, port=args.port)
        return 0

    if args.command == "reprocess":
        pipeline = Pipeline(cfg)
        d = pipeline.reprocess(args.invoice_id, args.pdf)
        print(f"{d.file_id}: {d.result.value}")
        return 0

    if args.command == "clean":
        clean_targets = _clean_targets(cfg, args)
        if not args.yes:
            print("se borrará:")
            for t in clean_targets:
                print(f"  {t}")
            if input("¿continuar? [y/N] ").strip().lower() not in {"y", "yes", "s", "si", "sí"}:
                print("cancelado")
                return 1
        for t in clean_targets:
            if t.is_dir():
                shutil.rmtree(t)
            elif t.exists():
                t.unlink()
            else:
                continue
            print(f"borrado: {t}")
        return 0

    return 1


def _clean_targets(cfg: AppConfig, args: argparse.Namespace) -> list[Path]:
    return [cfg.pages_dir, cfg.root / "scans", cfg.root / "work"]


def _latest_run_id(store: PouchStore) -> str:
    decisions = [store.hydrate(d) for d in store.list("decision:")]
    if not decisions:
        sys.exit("no hay runs en el store")
    decisions.sort(key=lambda d: (d.get("timestamp", 0), d.get("_id", "")))
    latest = decisions[-1]
    run_id = latest.get("run_id")
    if not run_id:
        sys.exit("no hay runs en el store")
    return str(run_id)


if __name__ == "__main__":
    raise SystemExit(main())
