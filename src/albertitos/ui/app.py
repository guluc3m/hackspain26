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

from albertitos.resumen import datos_resumen
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

# ---------------------------------------------------------------- Modo Alberto
# Lenguaje llano (AGENTS.md §9): toda jerga técnica se traduce; el detalle
# técnico queda en los tooltips (title=) y en la pantalla Ayuda.

NOMBRES_RUNG: dict[str, str] = {
    "rung1": "Texto del PDF",
    "rung2": "Código QR",
    "rung3": "OCR (leer escaneos)",
    "rung4": "Lector visual con IA (local)",
    "rung5": "Lector visual con IA (nube)",
}
NOMBRES_STAGE: dict[str, str] = {
    "extract:rung1_pdf_text": "Lectura del texto del PDF",
    "extract:rung2_raster_qr": "Renderizado + lectura del QR",
    "extract:rung3_tesseract": "OCR sobre la imagen",
    "extract:rung4_vlm": "Lector visual con IA (local)",
    "extract:rung5_cloud_vlm": "Lector visual con IA (nube)",
    "features": "Extracción de datos",
    "parse": "Traducción a campos",
    "decision": "Decisión con reglas",
    "render": "Renderizado de la página",
}
NOMBRES_EXTRACTOR: dict[str, str] = {
    "pypdf": "Lectura directa del PDF",
    "pypdfium2": "Renderizado de páginas",
    "zxing": "Lector de códigos QR",
    "tesseract": "OCR",
    "vlm": "Lector visual (IA local)",
    "cloud_vlm": "Lector visual (IA en la nube)",
    "regex": "Buscador de patrones",
    "rule-engine": "Motor de reglas",
    "parser": "Traducción a campos",
}
NOMBRES_DRILL: dict[str, str] = {
    "rung5-provider-caido": "El lector de la nube caído",
    "backoff-429": "Demasiadas peticiones: espera y reintenta",
    "crash-reanudacion": "Apagón a mitad de lote: reanuda sin duplicados",
    "ledger-corrupto": "Registro dañado: se tolera sin inventar",
}
GLOSARIO: list[tuple[str, str]] = [
    ("PAGAR", "Factura con todas las reglas en verde: se puede pagar."),
    ("NO_PAGAR", "Factura con una regla en rojo: no se paga y el motivo queda registrado."),
    ("ESCALAR", "Necesita que un humano la mire: la decisión la toma Alberto en la cola de Revisión."),
    ("Texto del PDF (rung 1)", "Lectura directa del texto que trae el PDF, sin fotos."),
    ("Código QR (rung 2)", "Código cuadrado que traen algunas facturas con sus datos dentro."),
    ("OCR (rung 3)", "Reconocimiento de texto sobre la imagen de la página (tesseract)."),
    ("Lector visual con IA (rung 4)", "Modelo de IA local que lee la página como imagen (llama-server)."),
    ("Lector visual con IA en la nube (rung 5)", "Misma idea, pero en un servicio externo. Solo si la local no basta."),
    ("Registro de actividad (ledger)", "Fichero al que solo se añade, donde queda guardado todo lo que pasa (para poder repetir y auditar)."),
    ("Base de datos local (store)", "Fichero SQLite con las decisiones y su evidencia; vive en .sdd/."),
    ("Cache", "Las páginas ya leídas no se vuelven a leer: se reutilizan (ahorra tiempo y dinero)."),
    ("Override", "La corrección que Alberto guarda en Revisión: queda sellada con quién y cuándo."),
    ("Regla (TOTALS_MUST_MATCH, …)", "Comprobación en código con su nombre exacto del contrato; cada decisión lista las reglas que la justifican."),
]


def _maestro_para_resumen() -> Path | None:
    """Maestro real para el resumen ejecutivo (auto-detectado, SOLO LECTURA)."""
    candidatos = [
        Path(".sdd/lote1/FINAL_v7_DEFINITIVO_ahorasi.xlsx"),
        Path("/home/deploy/hackspain26/caja-de-alberto/FINAL_v7_DEFINITIVO_ahorasi.xlsx"),
        Path("caja-de-alberto/FINAL_v7_DEFINITIVO_ahorasi.xlsx"),
    ]
    for c in candidatos:
        if c.is_file():
            return c
    return None


def _pendiente_alberto(store_root: Path) -> dict[str, Any]:
    """Lo primero que Alberto quiere saber: qué hay pendiente y por cuánto."""
    maestro = _maestro_para_resumen()
    try:
        datos = datos_resumen(store_root, maestro_path=maestro) if maestro else None
    except Exception:  # noqa: BLE001 — sin maestro el resumen degrada, no rompe
        datos = None
    if not datos:
        return {"n": None, "euros": None, "nota": "PENDIENTE: sin maestro en este nodo"}
    return {
        "n": datos["revisar"]["n"],
        "euros": datos["riesgo"]["total_en_riesgo_eur"],
        "pagado_n": datos["pago"]["n"],
        "pagado_total": datos["pago"]["total_eur"],
        "no_pago_n": datos["no_pago"]["n"],
        "nota": "",
    }

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
        base = Path(store_dir) if store_dir else None
        if base is None:
            # Modo Alberto: el store real del lote vive en .sdd/lote1/ledger
            # (copia congelada tras la corrida). Usa .sdd/ledger solo si tiene
            # contenido; si no, el lote 1; si no, demo.
            candidatos = [Path(".sdd") / "ledger", Path(".sdd") / "lote1" / "ledger"]
            base = next(
                (c for c in candidatos
                 if (c / "ledger.jsonl").is_file()
                 and (c / "ledger.jsonl").stat().st_size > 0),
                candidatos[0],
            )
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
    aplicacion.state.pendiente: dict[str, Any] | None = None
    aplicacion.state.store_base = (Path(store_dir) if store_dir else Path(".sdd") / "ledger")

    def _store_root() -> Path:
        """Raíz del store (donde vive store.db) — SOLO LECTURA."""
        return aplicacion.state.store_base.parent

    def ctx(**extra: Any) -> dict[str, Any]:
        datos: dict[str, Any] = {
            "demo": demo,
            "runner": estado,
            "drills": drills,
            "nombres_rung": NOMBRES_RUNG,
            "nombres_extractor": NOMBRES_EXTRACTOR,
            "nombres_stage": NOMBRES_STAGE,
            "nombres_drill": NOMBRES_DRILL,
            "glosario": GLOSARIO,
        }
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
    @aplicacion.get("/", response_class=HTMLResponse)
    def operaciones(request: Request):
        stats = stats_por_rung(aplicacion.state.registros)
        vlm = stats_vlm(aplicacion.state.registros, cache_root=_cache_root())
        sondea = _sonda_con_cache()
        if aplicacion.state.pendiente is None:
            aplicacion.state.pendiente = _pendiente_alberto(_store_root())
        return _TEMPLATES.TemplateResponse(
            request,
            "operaciones.html",
            ctx(
                resumen=ops_summary(aplicacion.state.view),
                escalera=stats["ventanas"],
                vlm=vlm,
                llama=sondea,
                pendiente=aplicacion.state.pendiente,
            ),
        )

    @aplicacion.get("/ayuda", response_class=HTMLResponse)
    def ayuda(request: Request):
        return _TEMPLATES.TemplateResponse(request, "ayuda.html", ctx())

    @aplicacion.get("/resumen-ejecutivo", response_class=HTMLResponse)
    def resumen_ejecutivo(request: Request):
        """«¿Qué pago hoy y por qué?» — se genera y se muestra, sin terminal."""
        try:
            maestro = _maestro_para_resumen()
            datos = datos_resumen(_store_root(), maestro) if maestro else None
        except Exception:  # noqa: BLE001 — degrada con aviso, no rompe
            datos = None
        if not datos:
            return _TEMPLATES.TemplateResponse(
                request,
                "resumen_ejecutivo.html",
                ctx(datos=None, error="No pude generar el resumen: falta el maestro de proveedores en este nodo."),
            )
        return _TEMPLATES.TemplateResponse(
            request, "resumen_ejecutivo.html", ctx(datos=datos)
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
# uvicorn directo: mismo contrato que desktop/launcher — vacío ⇒ cadena de
# fallback de create_app (.sdd/ledger → .sdd/lote1/ledger → demo)
app = create_app(
    store_dir=(
        Path(os.environ["ALBERTITOS_STORE"])
        if os.environ.get("ALBERTITOS_STORE", "").strip()
        else None
    )
)
