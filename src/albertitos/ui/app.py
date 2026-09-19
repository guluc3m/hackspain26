"""UI de operaciones — FastAPI + Jinja2 + HTMX (AGENTS.md §9).

La UI es producto, no herramienta de debug: español llano, sin JSON en el
flujo principal, y los números se muestran a secas (sin etiquetas de origen).

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

import base64
import json
import os
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from albertitos.emit import list_pdf_files_recursivo
from albertitos.telemetria import EventChain, stats_por_rung, stats_vlm

from .demo import demo_records
from .ledger import (
    OverrideView,
    build_view,
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
DESCRIPCIONES_REGLAS: dict[str, str] = {
    "NIF_IN_MASTER": "El NIF/CIF del emisor debe estar dado de alta en tu maestro de proveedores (el alta nunca es automática).",
    "IBAN_MATCHES_MASTER": "El IBAN de la factura debe coincidir con el que figura en tu maestro para ese proveedor (evita pagos a cuentas suplantadas).",
    "ORDER_BELONGS_TO_SUPPLIER": "El pedido que trae la factura debe corresponder a ese proveedor en tu registro de pedidos.",
    "ORDER_AMOUNT_MATCHES": "El importe de la factura debe cuadrar con el importe del pedido asociado.",
    "TOTALS_MUST_MATCH": "La suma de líneas (base + IVA) debe cuadrar con el total que declara la factura.",
    "IVA_CONSISTENT": "El IVA debe ser coherente: el tipo aplicado por su base da la cuota que declara la factura.",
    "DATE_VALID_NOT_FUTURE": "La fecha de la factura debe ser válida y no puede estar en el futuro.",
    "ORDER_PENDING": "El pedido debe seguir pendiente de pago (ni pagado ya ni cerrado).",
    "NO_DOUBLE_PAYMENT": "No debe existir ya un pago registrado para ese pedido o factura (duplicados).",
    "NO_EMBEDDED_INSTRUCTIONS": "El documento no debe contener órdenes escritas dentro (p. ej. «dar de alta y pagar»): los documentos son datos, no instrucciones.",
    "PROVEEDOR_FANTASMA": "Detecta proveedores «fantasma»: p. ej. el mismo IBAN usado por varias empresas de golpe.",
    "AMOUNT_OUTLIER": "El importe es un valor atípico: se dispara mucho respecto a lo habitual de ese proveedor.",
    "PEDIDO_EN_REVISION": "El pedido asociado está marcado en revisión: espera una decisión humana.",
    "REGLA_V4": "Regla de pago v4, cargada como datos desde rules/regla_v4.yaml sin tocar el motor.",
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
    """Maestro real (SOLO LECTURA), auto-detectado SIN rutas de ninguna
    máquina concreta: primero la variable de entorno ALBERTITOS_MAESTRO,
    después las ubicaciones relativas del proyecto. Así la app funciona en
    el ordenador de Alberto y en cualquier otro sitio."""
    env = os.environ.get("ALBERTITOS_MAESTRO", "").strip()
    candidatos = [Path(env)] if env else []
    candidatos += [
        Path(".sdd/lote1/FINAL_v7_DEFINITIVO_ahorasi.xlsx"),
        Path("caja-de-alberto/FINAL_v7_DEFINITIVO_ahorasi.xlsx"),
    ]
    for c in candidatos:
        if c.is_file():
            return c
    return None


def _pendiente_alberto(store_root: Path) -> dict[str, Any]:
    """Lo primero que Alberto quiere saber: qué hay pendiente. Se calcula
    del propio store (conteos por resultado), sin maestro ni Excel: la app
    funciona con cualquier lote en cualquier ordenador."""
    try:
        raiz = Path(store_root)
        decisiones = None
        if (raiz / "store.db").is_file():
            from albertitos.store import Store

            decisiones = Store(raiz).all_decisions()
    except Exception:  # noqa: BLE001 — sin store aún, degrada honesto
        decisiones = None
    if decisiones is None:
        return {
            "n": None,
            "pagado_n": None,
            "pagado_total": None,
            "no_pago_n": None,
            "nota": "PENDIENTE: sin store en este nodo",
        }
    conteo: dict[str, int] = {}
    for d in decisiones:
        conteo[d.result] = conteo.get(d.result, 0) + 1
    return {
        "n": {"valor": str(conteo.get("ESCALAR", 0))},
        "pagado_n": {"valor": str(conteo.get("PAGAR", 0))},
        "pagado_total": {"valor": "—"},
        "no_pago_n": {"valor": str(conteo.get("NO_PAGAR", 0))},
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


def _procesar_carpeta_real(carpeta: Path) -> dict[str, Any]:
    """Procesa la carpeta que Alberto eligió con el runner end-to-end.

    Sin rutas de ninguna máquina: el maestro se auto-detecta (env
    ALBERTITOS_MAESTRO o layout relativo del proyecto) y las reglas viajan
    con el paquete. El escaneo es RECURSIVO (subcarpetas incluidas) y el
    lote es reanudable: re-procesar lo ya decidido es un no-op.
    """
    from albertitos.run import DEFAULT_RULES, Runner, RunnerConfig

    maestro = _maestro_para_resumen()
    if maestro is None:
        return {
            "estado": "error",
            "mensaje": (
                "No encontré el maestro de proveedores (el Excel). Ponlo en "
                "caja-de-alberto/ o indica su ruta en la variable "
                "ALBERTITOS_MAESTRO y vuelve a intentarlo."
            ),
        }
    try:
        cfg = RunnerConfig(
            facturas_dir=carpeta,
            outcomes_path=Path("outcomes.jsonl"),
            store_root=Path(".sdd"),
            rules_yaml=DEFAULT_RULES,
            master_path=maestro,
            fecha_referencia=datetime.now(tz=UTC).date().isoformat(),
            run_id="ui",
            recursivo=True,
        )
        runner = Runner(cfg)
        report = runner.run()
        # Entregable del contrato (AGENTS.md §1): outcomes.jsonl con los
        # file_id de ESTA carpeta (emisión determinista, sin duplicar lote 1).
        from albertitos.emit import emit_outcomes

        emit_outcomes(runner.store, cfg.outcomes_path,
                      only_files={p.name for p in runner.files()})
        runner.store.close()
    except Exception as e:  # noqa: BLE001 — un lote que falla degrada con mensaje, no tumba la UI
        return {
            "estado": "error",
            "mensaje": f"No pude procesar el lote: {e}",
        }
    terminados = report.procesados + report.reutilizados
    return {
        "estado": "listo",
        "mensaje": (
            f"Lote terminado: {report.total} factura(s) en la carpeta, "
            f"{terminados} decididas ({report.reutilizados} ya lo estaban, "
            f"{report.timeout} por esperar demasiado). Mira la pestaña "
            "Facturas."
        ),
    }


def create_app(
    store_dir: Path | None = None,
    records: list[dict[str, Any]] | None = None,
    override_dir: Path | None = None,
    procesador: Callable[[Path], dict[str, Any]] | None = None,
) -> FastAPI:
    """Fábrica de la app. `records` inyecta registros (tests); si no, se lee
    el ledger en `store_dir` (por defecto `.sdd/ledger/`; el lote real vive en
    `.sdd/lote1/ledger`, symlink SOLO LECTURA) en solo lectura.

    `procesador` (tests) sustituye al runner real para la carpeta que el
    usuario elige en Operaciones; por defecto es el runner end-to-end.

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
    else:
        registros = records
        destino = override_dir
        estado = None

    aplicacion.state.view = build_view(registros)
    aplicacion.state.registros = registros
    aplicacion.state.override_dir = destino
    aplicacion.state.demo = demo
    aplicacion.state.runner = estado
    aplicacion.state.pendiente: dict[str, Any] | None = None
    aplicacion.state.store_base = (Path(store_dir) if store_dir else Path(".sdd") / "ledger")
    # Lote elegido por el usuario en Operaciones: estado del trabajo en curso
    # (None = todavía no se ha procesado ninguna carpeta).
    aplicacion.state.lote: dict[str, Any] | None = None
    # De dónde se leyó el ledger (para recargarlo cuando el lote termine).
    aplicacion.state.ledger_base = base if records is None else None
    # Procesador del lote: el runner real, o el que inyecten los tests.
    aplicacion.state.procesador = procesador if procesador is not None else _procesar_carpeta_real

    def _recargar_registros() -> None:
        """Tras procesar un lote, la UI lee de nuevo el ledger (el store ya
        tiene las decisiones nuevas); Alberto las ve sin reiniciar nada."""
        base_ledger = aplicacion.state.ledger_base
        if base_ledger is None:
            return
        registros_nuevos = load_ledger(base_ledger)
        cola_rev = base_ledger.parent / "review-queue"
        if cola_rev.is_dir():
            registros_nuevos += load_ledger(cola_rev)
        if registros_nuevos:
            aplicacion.state.registros = registros_nuevos
            aplicacion.state.view = build_view(registros_nuevos)
            aplicacion.state.demo = False
            aplicacion.state.pendiente = None

    def _store_root() -> Path:
        """Raíz del store (donde vive store.db) — SOLO LECTURA."""
        return aplicacion.state.store_base.parent

    def ctx(**extra: Any) -> dict[str, Any]:
        datos: dict[str, Any] = {
            "demo": demo,
            "runner": estado,
            "nombres_rung": NOMBRES_RUNG,
            "nombres_extractor": NOMBRES_EXTRACTOR,
            "nombres_stage": NOMBRES_STAGE,
            "nombres_drill": NOMBRES_DRILL,
            "descripciones_reglas": DESCRIPCIONES_REGLAS,
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
                lote=aplicacion.state.lote,
            ),
        )

    @aplicacion.post("/operaciones/procesar")
    async def procesar_lote(carpeta: str = Form(...)):
        """Alberto pega la ruta de UNA carpeta cualquiera (Windows/mac/Linux)
        y la app la escanea en profundidad buscando PDFs y los procesa.

        Nunca se escribe en la carpeta elegida: el store y los resultados
        viven en `.sdd/` del proyecto. El trabajo corre en segundo plano:
        la página responde al instante y el estado se ve aquí mismo.
        """
        texto = carpeta.strip().strip('"').strip("'")
        ruta = Path(texto).expanduser()
        if aplicacion.state.lote and aplicacion.state.lote.get("estado") == "procesando":
            aplicacion.state.lote["mensaje"] = (
                "Ya hay un lote procesándose (" + aplicacion.state.lote.get("carpeta", "")
                + "). Espera a que termine antes de lanzar otro."
            )
            return RedirectResponse("/", status_code=303)
        pdfs = list_pdf_files_recursivo(ruta)
        if not ruta.is_dir():
            aplicacion.state.lote = {
                "estado": "error",
                "mensaje": f"La carpeta «{texto}» no existe o no puedo leerla. Revisa la ruta.",
            }
        elif not pdfs:
            aplicacion.state.lote = {
                "estado": "error",
                "mensaje": (
                    f"En «{texto}» no hay ningún PDF (busqué también en sus "
                    "subcarpetas). Comprueba que es la carpeta de las facturas."
                ),
            }
        else:
            procesador = aplicacion.state.procesador
            aplicacion.state.lote = {
                "estado": "procesando",
                "carpeta": str(ruta),
                "n_pdfs": len(pdfs),
                "mensaje": f"Procesando {len(pdfs)} factura(s) de «{ruta}»…",
            }

            def _trabajo() -> None:
                try:
                    resultado = procesador(ruta)
                except Exception as e:  # noqa: BLE001 — el fallo se muestra, la UI sigue
                    resultado = {"estado": "error", "mensaje": f"No pude procesar el lote: {e}"}
                resultado.setdefault("carpeta", str(ruta))
                aplicacion.state.lote = resultado
                _recargar_registros()

            threading.Thread(target=_trabajo, daemon=True).start()
        return RedirectResponse("/", status_code=303)

    @aplicacion.get("/ayuda", response_class=HTMLResponse)
    def ayuda(request: Request):
        return _TEMPLATES.TemplateResponse(request, "ayuda.html", ctx())

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

    @aplicacion.get("/revision/imagen/{invoice_id}/{pagina}")
    def revision_imagen(invoice_id: str, pagina: int):
        """PNG de la página servido aparte (NO base64 en el HTML): con imágenes
        de ~1-6 MB por página, el HTML de /revision pesaba decenas de MB y el
        navegador tardaba o colgaba. Así la página es ligera y la imagen la
        pide el <img> de una en una. SOLO LECTURA."""
        b64 = (aplicacion.state.view.images_by_invoice.get(invoice_id) or {}).get(pagina)
        if not b64:
            raise HTTPException(status_code=404, detail="sin imagen almacenada")
        try:
            png = base64.b64decode(b64)
        except (ValueError, TypeError):
            raise HTTPException(status_code=404, detail="imagen corrupta") from None
        return Response(content=png, media_type="image/png",
                        headers={"Cache-Control": "max-age=86400"})

    @aplicacion.get("/facturas/{invoice_id}/pdf")
    def factura_pdf(invoice_id: str):
        """PDF original servido inline para verlo en la UI. La carpeta de PDFs
        NO está hardcodeada: ALBERTITOS_CARPETA (o candidates relativos), y se
        busca el file_id EXACTO (basename) recursivamente dentro."""
        vista = aplicacion.state.view
        file_id = next(
            (d.file_id for d in vista.decisions
             if d.invoice_id == invoice_id and d.file_id),
            invoice_id,
        )
        if not file_id or file_id.startswith("—"):
            raise HTTPException(status_code=404, detail="esta factura aún no tiene PDF asociado")
        env = os.environ.get("ALBERTITOS_CARPETA", "").strip()
        if env:
            candidatos = [Path(env)]  # la carpeta del usuario manda
        else:
            candidatos = [Path("facturas"), Path("caja-de-alberto/facturas")]
        ruta = next(
            (p for c in candidatos if c.is_dir() for p in c.rglob(file_id) if p.is_file()),
            None,
        )
        if ruta is None:
            raise HTTPException(
                status_code=404,
                detail=f"PDF {file_id} no encontrado — configura ALBERTITOS_CARPETA con la carpeta de facturas",
            )
        return Response(
            content=ruta.read_bytes(),
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="{file_id}"'},
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
