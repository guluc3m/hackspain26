"""Tests de T29: sonda de health del rung 4 con 4 estados del stub.

Estados: MUERTO (conexión rechazada ⇒ skip definitivo, cacheable) /
CARGANDO (/health 503 ⇒ backoff acotado, skip NO cacheable) / COLGADO
(acepta conexiones y no contesta ⇒ backoff, skip NO cacheable) / SANO
(rung 4 responde). Cada rama con su motivo en la evidencia.
"""

from __future__ import annotations

import shutil
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from albertitos.extract.config import ExtractionConfig
from albertitos.extract.ladder import ExtractionLadder

REPO = Path(__file__).resolve().parent.parent
# T40F2: sin puertos fijos (bind :0) y sin directorio compartido: cada test
# usa tmp_path de pytest (aislado por test y por proceso).
SCAN = REPO / "tests/fixtures/scans/scan_001.pdf"


class StubVLM:
    """llama-server de mentira con MODOS: sano / muerto / cargando / colgado.

    - muerto: socket cerrado ⇒ conexión rechazada.
    - cargando: /v1/models 200, /health 503 (+ Retry-After opcional).
    - colgado: /v1/models 200, /health acepta y NUNCA responde.
    - sano: /v1/models 200, /health 200, chat responde.
    """

    def __init__(self, port: int):
        self.port = port
        self.modo = "sano"
        self.retry_after = None
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    # -----------------------------------------------------------------

    def _handler(self):
        stub = self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self) -> None:
                if self.path.startswith("/v1/models") and stub.modo != "muerto":
                    body = b'{"models":[{"name":"stub-vl"}]}'
                    self._resp(200, body)
                elif self.path.startswith("/health"):
                    if stub.modo == "cargando":
                        if stub.retry_after:
                            self.send_response(503)
                            self.send_header("Retry-After", str(stub.retry_after))
                            self.send_header("Content-Length", "0")
                            self.end_headers()
                        else:
                            self._resp(503, b'{"status":"loading"}')
                    elif stub.modo == "colgado":
                        time.sleep(5)  # el sonda usa timeout corto ⇒ 'hung'
                    elif stub.modo == "sano":
                        self._resp(200, b'{"status":"ok"}')
                    else:
                        self.close_connection = True
                else:
                    self._resp(404, b"{}")

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", 0))
                self.rfile.read(length)
                lectura = '{"nif":"","iban":"","fecha":"","total":"","pedido":"","proveedor":""}'
                body = ('{"choices":[{"message":{"content":"'
                        + lectura.replace('"', '\\"') + '"}}]}').encode()
                self._resp(200, body)

            def _resp(self, code: int, body: bytes) -> None:
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args) -> None:
                pass

        return H

    def start(self) -> None:
        # T40F2: bind :0 ⇒ puerto efímero del SO; leemos el real para `url`.
        self._httpd = ThreadingHTTPServer(("127.0.0.1", self.port),
                                          self._handler())
        self.port = self._httpd.server_address[1]
        self._httpd.daemon_threads = True
        self._thread = threading.Thread(target=self._httpd.serve_forever,
                                        daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.modo = "muerto"
        if self._httpd is not None:
            threading.Thread(target=self._httpd.shutdown, daemon=True).start()
            if self._thread is not None:
                self._thread.join(timeout=5)
            self._httpd.server_close()
            self._httpd = None
            self._thread = None


def _cfg(stub: StubVLM) -> ExtractionConfig:
    """Sonda rápida: reintentos acotados y backoff corto (tests)."""
    from dataclasses import replace

    base = ExtractionConfig()
    return replace(
        base,
        vlm_base_url=stub.url,
        vlm_probe_timeout_s=0.5,
        vlm_health_retries=2,
        vlm_health_backoff_cap_s=0.1,
    )


def _rung4_rows(rutas: Path) -> list[dict]:
    import sqlite3

    conn = sqlite3.connect(rutas / "store.db")
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(
            "SELECT stage, outcome, detail FROM evidence "
            "WHERE stage='extract:rung4_vlm' ORDER BY id"
        ).fetchall()]
    finally:
        conn.close()


def _extract(stub: StubVLM, nombre: str, *, base: Path,
             cache_fresh: bool = False):
    """Extrae con la config del stub. `cache_fresh=True` borra el cache
    ANTES (corrida 1); False conserva el cache (corrida 2 = re-run).
    `base` es tmp_path de pytest (T40F2: nada compartido entre tests)."""
    if cache_fresh and (base / "cache").exists():
        shutil.rmtree(base / "cache")
    from albertitos.extract.ladder import ExtractionLadder

    lad = ExtractionLadder(cfg=_cfg(stub), cache_root=base / "cache",
                           review_dir=base / "review")
    return lad.extract_file(SCAN, invoice_id="inv-t29", file_id=nombre)


def test_estado_muerto_skip_definitivo_y_cacheado(tmp_path):
    stub = StubVLM(0)
    stub.modo = "muerto"  # sin arrancar: conexión rechazada
    primera = _extract(stub, "muerto", base=tmp_path, cache_fresh=True)
    skips = [ev for ev in primera[0].evidence if ev.stage == "extract:rung4_vlm"]
    assert len(skips) == 1
    assert "skipped:llama-server-down" in skips[0].detail
    # DEFINITIVO ⇒ cacheado: el segundo run es cache_hit (no re-intenta)
    segunda = _extract(stub, "muerto", base=tmp_path)
    hits = [ev for ev in segunda[0].evidence if ev.outcome == "cache_hit"
            and ev.stage == "extract:rung4_vlm"]
    assert len(hits) == 1  # replay, 0 re-intentos


def test_estado_cargando_backoff_limitado_y_no_cacheado(tmp_path):
    stub = StubVLM(0)
    stub.modo = "cargando"
    stub.retry_after = 0.2
    stub.start()
    try:
        primera = _extract(stub, "cargando", base=tmp_path, cache_fresh=True)
        skips = [ev for ev in primera[0].evidence
                 if ev.stage == "extract:rung4_vlm"]
        assert len(skips) == 1
        d = skips[0].detail
        assert "skipped:llama-server-loading" in d
        assert "reintentos=2" in d  # backoff acotado: 2 reintentos del config
        # NO cacheable: la página queda PENDIENTE para re-proceso — el re-run
        # vuelve a intentar (no hay cache_hit del rung 4)
        segunda = _extract(stub, "cargando", base=tmp_path)
        hits = [ev for ev in segunda[0].evidence if ev.outcome == "cache_hit"
                and ev.stage == "extract:rung4_vlm"]
        assert hits == []
        skips2 = [ev for ev in segunda[0].evidence
                  if ev.stage == "extract:rung4_vlm" and ev.outcome == "skipped"]
        assert len(skips2) == 1
    finally:
        stub.stop()


def test_estado_colgado_timeout_de_sonda_y_no_cacheado(tmp_path):
    stub = StubVLM(0)
    stub.modo = "colgado"
    stub.start()
    try:
        primera = _extract(stub, "colgado", base=tmp_path, cache_fresh=True)
        skips = [ev for ev in primera[0].evidence
                 if ev.stage == "extract:rung4_vlm"]
        assert len(skips) == 1
        assert "skipped:llama-server-hung" in skips[0].detail
        assert "reintentos=2" in skips[0].detail
        # no cacheable: re-run reintenta
        segunda = _extract(stub, "colgado", base=tmp_path)
        skips2 = [ev for ev in segunda[0].evidence
                  if ev.stage == "extract:rung4_vlm" and ev.outcome == "skipped"]
        assert len(skips2) == 1
    finally:
        stub.stop()


def test_estado_sano_rung4_responde(tmp_path):
    stub = StubVLM(0)
    stub.modo = "sano"
    stub.start()
    try:
        out = _extract(stub, "sano", base=tmp_path, cache_fresh=True)
        rows = [ev for ev in out[0].evidence if ev.stage == "extract:rung4_vlm"]
        assert len(rows) == 1
        assert rows[0].outcome in ("accept", "below-threshold")
        assert "skipped" not in (rows[0].detail or "")
    finally:
        stub.stop()


def test_cargando_tras_el_limite_la_pagina_queda_pendiente(tmp_path):
    """'cargando' N veces ⇒ tras el límite de reintentos, skip con motivo y
    el lote sigue; la página NO queda cacheada como fallida definitiva."""
    stub = StubVLM(0)
    stub.modo = "cargando"
    stub.start()
    try:
        for corrida in range(3):  # 3 corridas seguidas en 'cargando'
            out = _extract(stub, f"cargando{corrida}", base=tmp_path,
                           cache_fresh=True)
            skips = [ev for ev in out[0].evidence
                     if ev.stage == "extract:rung4_vlm"
                     and ev.outcome == "skipped"]
            assert len(skips) == 1
            assert "skipped:llama-server-loading" in skips[0].detail
        # y el store de la 3ª corrida no trae cache_hit del rung 4: pendiente
        tercera = _extract(stub, "cargando-check", base=tmp_path)  # cache NO borrado
        hits = [ev for ev in tercera[0].evidence
                if ev.outcome == "cache_hit" and ev.stage == "extract:rung4_vlm"]
        assert hits == []
    finally:
        stub.stop()


def test_transicion_cargando_a_sano_se_recupera(tmp_path):
    """El caso REAL del drill T24: 'cargando' → (backoff) → 'sano' ⇒ el rung
    4 responde sin degradar. Con reintentos suficientes, la página se extrae
    normal en la MISMA pasada."""
    stub = StubVLM(0)
    stub.modo = "cargando"
    stub.start()
    try:
        from dataclasses import replace
        from threading import Timer

        # tras 0.4s el modelo acaba de cargar (mismo run)
        def sano():
            stub.modo = "sano"

        Timer(0.4, sano).start()
        lad = ExtractionLadder(
            cfg=replace(_cfg(stub), vlm_health_retries=5,
                        vlm_health_backoff_cap_s=0.3),
            cache_root=tmp_path / "cache", review_dir=tmp_path / "review")
        out = lad.extract_file(SCAN, invoice_id="inv-t29b", file_id="recupera")
        rows = [ev for ev in out[0].evidence if ev.stage == "extract:rung4_vlm"]
        assert len(rows) == 1
        assert rows[0].outcome in ("accept", "below-threshold")
    finally:
        stub.stop()


def test_reintentos_health_dejan_evidencia_por_intento(tmp_path):
    """T33-M4: cada reintento de health del rung 4 queda en evidencia
    (stage extract:rung4_health) — la pantalla Salud puede contarlo."""
    stub = StubVLM(0)
    stub.modo = "cargando"
    stub.start()
    try:
        out = _extract(stub, "reintentos", base=tmp_path, cache_fresh=True)
        filas = [ev for ev in out[0].evidence
                 if ev.stage == "extract:rung4_health"]
        assert len(filas) == 2  # vlm_health_retries=2 en la config del test
        assert all(ev.outcome == "retry" for ev in filas)
        assert "cargando" in filas[0].detail
        # y los contadores de rung4_vlm no cambian de forma
        skips = [ev for ev in out[0].evidence
                 if ev.stage == "extract:rung4_vlm" and ev.outcome == "skipped"]
        assert len(skips) == 1
    finally:
        stub.stop()
