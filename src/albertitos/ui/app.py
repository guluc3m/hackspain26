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
import os
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from albertitos.telemetria import EventChain, stats_por_rung, stats_vlm

from .demo import demo_records
from .ledger import (
    OverrideView,
    build_view,
    drills_estado,
    estado_runner,
    factura_detalle,
    facturas_rows,
    health,
    load_ledger,
    ops_summary,
    reglas_activas,
    revision_queue,
    what_if,
)

_sonda_cache: tuple[float, Any] | None = None  # (ts, resultado) — sonda acotada


def _ruta_actividad() -> Path:
    """Cadena de actividad: telemetría de la UI, JAMÁS dentro del store."""
    return Path(".sdd") / "telemetria" / "actividad.jsonl"


def _cache_root() -> Path | None:
    candidato = Path(".sdd/lote1/cache")
    return candidato if candidato.is_dir() else None


def _sonda_con_cache(base_url: str = "http://127.0.0.1:8080", ttl_s: float = 60.0) -> Any:
    """Sonda llama-server con caché de 60 s: nunca satura el sidecar."""
    global _sonda_cache
    ahora = time.monotonic()
    if _sonda_cache is not None and ahora - _sonda_cache[0] < ttl_s:
        return _sonda_cache[1]
    from albertitos.telemetria import sonda_llama

    resultado = sonda_llama(base_url)
    _sonda_cache = (ahora, resultado)
    return resultado



_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _override_destino(store_dir: Path) -> Path:
    """Cola de overrides: SIEMPRE en el `.sdd/` local del worktree de la UI.

    Los stores externos (p. ej. `.sdd/lote1` → worktree de W1) son SOLO
    LECTURA: ni el ledger ni su review-queue se tocan jamás.
    """
    return Path(".sdd") / "review-queue" / "overrides.jsonl"


def create_app(
    store_dir: Path | None = None,
    records: list[dict[str, Any]] | None = None,
    override_dir: Path | None = None,
) -> FastAPI:
    """Fábrica de la app. `records` inyecta registros (tests); si no, se lee
    el ledger en `store_dir` (por defecto `.sdd/ledger/`; el lote real vive en
    `.sdd/lote1/ledger`, symlink SOLO LECTURA) en solo lectura.

    Si el ledger lleva el `review-queue` hermano (cola de revisión con campos
    e imágenes), se carga también — ambos en SOLO LECTURA.
    """
    aplicacion = FastAPI(title="Albertitos — Operaciones", docs_url=None, redoc_url=None)

    demo = records is None
    if records is None:
        base = Path(store_dir) if store_dir else Path(".sdd") / "ledger"
        registros = load_ledger(base)
        # cola de revisión del lote real (campos + imágenes por página)
        cola_rev = base.parent / "review-queue"
        if cola_rev.is_dir():
            registros += load_ledger(cola_rev)
        if not registros:
            registros = demo_records()
        else:
            demo = False
        destino = override_dir if override_dir is not None else _override_destino(base)
        estado = estado_runner(base)
        drills = drills_estado()
    else:
        registros = records
        destino = override_dir
        estado = None
        drills = None

    aplicacion.state.view = build_view(registros)
    aplicacion.state.registros = registros
    aplicacion.state.override_dir = destino
    aplicacion.state.demo = demo
    aplicacion.state.runner = estado
    aplicacion.state.drills = drills

    def ctx(**extra: Any) -> dict[str, Any]:
        datos: dict[str, Any] = {"demo": demo, "runner": estado, "drills": drills}
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
        stats = stats_por_rung(aplicacion.state.registros)
        vlm = stats_vlm(aplicacion.state.registros, cache_root=_cache_root())
        sondea = _sonda_con_cache()
        return _TEMPLATES.TemplateResponse(
            request,
            "operaciones.html",
            ctx(
                resumen=ops_summary(aplicacion.state.view),
                escalera=stats["ventanas"],
                vlm=vlm,
                llama=sondea,
            ),
        )

    @aplicacion.get("/facturas", response_class=HTMLResponse)
    def facturas(
        request: Request,
        result: str = "",
        q: str = "",
        pagina: int = 1,
    ):
        filas = facturas_rows(aplicacion.state.view)
        if result:
            filas = [f for f in filas if f["result"] == result]
        if q:
            filas = [f for f in filas if q.casefold() in f["file_id"].casefold()]
        total = len(filas)
        por_pagina = 50
        n_paginas = max(1, -(-total // por_pagina))
        pagina = min(max(1, pagina), n_paginas)
        visibles = filas[(pagina - 1) * por_pagina : pagina * por_pagina]
        return _TEMPLATES.TemplateResponse(
            request,
            "facturas.html",
            ctx(
                filas=visibles,
                total=total,
                pagina=pagina,
                n_paginas=n_paginas,
                result=result,
                q=q,
                resultados=("PAGAR", "NO_PAGAR", "ESCALAR", "EN_PROCESO"),
            ),
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
    def revision(request: Request, pagina: int = 1):
        vista = aplicacion.state.view
        cola = revision_queue(vista)
        con_imagen = sum(1 for c in cola if c["imagenes"])
        por_pagina = 6
        n_paginas = max(1, -(-len(cola) // por_pagina))
        pagina = min(max(1, pagina), n_paginas)
        return _TEMPLATES.TemplateResponse(
            request,
            "revision.html",
            ctx(
                cola=cola[(pagina - 1) * por_pagina : pagina * por_pagina],
                n_cola=len(cola),
                con_imagen=con_imagen,
                pagina=pagina,
                n_paginas=n_paginas,
                overrides=vista.overrides,
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
        # telemetría: el evento de corrección queda en la cadena encadenada
        try:
            EventChain(_ruta_actividad()).append(
                "override-revision",
                {"invoice_id": invoice_id, "file_id": file_id, "campo": campo},
            )
        except OSError:
            pass  # la telemetría nunca bloquea la revisión
        return RedirectResponse("/revision", status_code=303)

    @aplicacion.get("/actividad", response_class=HTMLResponse)
    def actividad(request: Request):
        cadena = EventChain(_ruta_actividad())
        return _TEMPLATES.TemplateResponse(
            request,
            "actividad.html",
            ctx(
                eventos=cadena.leer()[-50:],
                integridad=cadena.verificar(),
                total=len(cadena.leer()),
            ),
        )

    @aplicacion.post("/actividad/anotar")
    async def actividad_anotar(nota: str = Form(...)):
        EventChain(_ruta_actividad()).append(
            "anotacion-humana",
            {"nota": nota, "quien": "alberto-ui"},
        )
        return RedirectResponse("/actividad", status_code=303)

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
        # con el formato real del runner (lote 1) los veredictos no registran
        # confianza por campo: el what-if lo dice explícitamente
        sin_confianza = bool(codigo) and not cambios and not any(
            "_confianza" in v.consumed
            for d in vista.decisions
            for v in d.verdicts
            if v.code == codigo
        )
        return _TEMPLATES.TemplateResponse(
            request,
            "reglas.html",
            ctx(
                activas=activas,
                codigo=codigo,
                nuevo_umbral=nuevo_umbral,
                cambios=cambios,
                error=error,
                sin_confianza=sin_confianza,
            ),
        )

    @aplicacion.get("/salud", response_class=HTMLResponse)
    def salud(request: Request):
        return _TEMPLATES.TemplateResponse(
            request, "salud.html", ctx(estado=health(aplicacion.state.view))
        )

    return aplicacion


# Store configurable por entorno: `ALBERTITOS_STORE=.sdd/lote1/ledger` para la
# demo con el lote 1 real (symlink SOLO LECTURA); default = `.sdd/ledger`.
app = create_app(store_dir=Path(os.environ.get("ALBERTITOS_STORE", ".sdd/ledger")))
