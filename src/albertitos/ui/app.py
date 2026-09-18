"""UI de operaciones — FastAPI + Jinja2 + HTMX (AGENTS.md §9).

La UI es producto, no herramienta de debug: español llano, sin JSON en el
flujo principal, y todo número etiquetado como **medido** o **estimado**.

Reglas duras (T5):
- La UI lee store/ledger en SOLO LECTURA y jamás decide.
- Las resoluciones humanas de la cola de ESCALAR no se escriben en el store:
  se encolan como overrides (con provenance) en `.sdd/review-queue/
  overrides.jsonl`, que el pipeline consume para re-extraer y dejar que el
  motor determinista recompute. La revisión nunca bloquea el pipeline.
- Si el ledger aún no tiene datos se sirven datos de prueba claramente
  marcados, para que Alberto pueda explorar la UI desde el primer minuto.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .demo import demo_records
from .ledger import (
    OverrideView,
    build_view,
    factura_detalle,
    facturas_rows,
    health,
    load_ledger,
    ops_summary,
    reglas_activas,
    revision_queue,
    what_if,
)

_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _override_destino(store_dir: Path) -> Path:
    """Cola de overrides: junto al ledger, pero JAMÁS dentro del store."""
    return store_dir.parent / "review-queue" / "overrides.jsonl"


def create_app(
    store_dir: Path | None = None,
    records: list[dict[str, Any]] | None = None,
    override_dir: Path | None = None,
) -> FastAPI:
    """Fábrica de la app. `records` inyecta registros (tests); si no, se lee
    el ledger en `store_dir` (por defecto `.sdd/ledger/`) en solo lectura."""
    aplicacion = FastAPI(title="Albertitos — Operaciones", docs_url=None, redoc_url=None)

    demo = records is None
    if records is None:
        base = Path(store_dir) if store_dir else Path(".sdd") / "ledger"
        registros = load_ledger(base)
        if not registros:
            registros = demo_records()
        else:
            demo = False
        destino = override_dir if override_dir is not None else _override_destino(base)
    else:
        registros = records
        destino = override_dir

    aplicacion.state.view = build_view(registros)
    aplicacion.state.override_dir = destino
    aplicacion.state.demo = demo

    def ctx(**extra: Any) -> dict[str, Any]:
        datos: dict[str, Any] = {"demo": demo}
        datos.update(extra)
        return datos

    def guardar_override(ov: OverrideView) -> None:
        destino_final = aplicacion.state.override_dir
        if destino_final is None:
            # Sin directorio de cola (tests/demo): los overrides viven en memoria.
            aplicacion.state.view.overrides.append(ov)
            return
        destino_final.parent.mkdir(parents=True, exist_ok=True)
        with destino_final.open("a", encoding="utf-8") as fh:
            fh.write(
                json.dumps(
                    {
                        "invoice_id": ov.invoice_id,
                        "file_id": ov.file_id,
                        "campo": ov.campo,
                        "valor": ov.valor,
                        "nota": ov.nota,
                        "cuando": ov.cuando,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    @aplicacion.get("/", response_class=HTMLResponse)
    def operaciones(request: Request):
        return _TEMPLATES.TemplateResponse(
            request, "operaciones.html", ctx(resumen=ops_summary(aplicacion.state.view))
        )

    @aplicacion.get("/facturas", response_class=HTMLResponse)
    def facturas(request: Request):
        return _TEMPLATES.TemplateResponse(
            request, "facturas.html", ctx(filas=facturas_rows(aplicacion.state.view))
        )

    @aplicacion.get("/facturas/{invoice_id}", response_class=HTMLResponse)
    def factura(request: Request, invoice_id: str):
        detalle = factura_detalle(aplicacion.state.view, invoice_id)
        if detalle is None:
            return _TEMPLATES.TemplateResponse(
                request,
                "no_encontrado.html",
                ctx(invoice_id=invoice_id),
                status_code=404,
            )
        return _TEMPLATES.TemplateResponse(
            request, "factura_detalle.html", ctx(invoice_id=invoice_id, **detalle)
        )

    @aplicacion.get("/revision", response_class=HTMLResponse)
    def revision(request: Request):
        return _TEMPLATES.TemplateResponse(
            request,
            "revision.html",
            ctx(
                cola=revision_queue(aplicacion.state.view),
                overrides=aplicacion.state.view.overrides,
            ),
        )

    @aplicacion.post("/revision/{invoice_id}/resolver")
    async def resolver(
        invoice_id: str,
        file_id: str = Form(...),
        campo: str = Form(...),
        valor: str = Form(...),
        nota: str = Form(""),
    ):
        guardar_override(
            OverrideView(
                invoice_id=invoice_id,
                file_id=file_id,
                campo=campo,
                valor=valor,
                nota=nota,
                cuando=time.strftime("%Y-%m-%d %H:%M:%S"),
            )
        )
        return RedirectResponse("/revision", status_code=303)

    @aplicacion.get("/reglas", response_class=HTMLResponse)
    def reglas(request: Request, codigo: str = "", nuevo_umbral: str = ""):
        vista = aplicacion.state.view
        activas = reglas_activas(vista)
        cambios: list[dict[str, Any]] = []
        error = ""
        if codigo and nuevo_umbral:
            try:
                cambios = what_if(vista, codigo, float(nuevo_umbral.replace(",", ".")))
            except ValueError:
                error = "El umbral debe ser un número entre 0 y 1."
        return _TEMPLATES.TemplateResponse(
            request,
            "reglas.html",
            ctx(
                activas=activas,
                codigo=codigo,
                nuevo_umbral=nuevo_umbral,
                cambios=cambios,
                error=error,
            ),
        )

    @aplicacion.get("/salud", response_class=HTMLResponse)
    def salud(request: Request):
        return _TEMPLATES.TemplateResponse(
            request, "salud.html", ctx(estado=health(aplicacion.state.view))
        )

    return aplicacion


app = create_app()
