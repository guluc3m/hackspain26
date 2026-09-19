"""Tests de T24: drill en vivo del rung 4 con STUB que muere (sin red real).

El stub es un llama-server OpenAI-compatible en un hilo: responde
/v1/models (health) y /v1/chat/completions. Al `kill`, deja de aceptar
conexiones (las llamadas nuevas fallan al instante, como un proceso muerto).
La recuperación vuelve a levantar el stub en el MISMO puerto.
"""

from __future__ import annotations

import json
import shutil
import threading
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from albertitos.drill_rung4_live import (
    DrillConfig,
    DrillHooks,
    ejecutar_drill,
)
from albertitos.run import _vlm_up

REPO = Path(__file__).resolve().parent.parent
DRILL_TMP = REPO / ".sdd" / "pytest-tmp" / "drill-live"
STUB_PORT = 8231
STUB_URL = f"http://127.0.0.1:{STUB_PORT}"


class StubLlamaServer:
    """llama-server de mentira: health + chat/completions con lectura fija.

    `stop()` = el proceso muere: conexiones nuevas rechazadas al instante,
    las ya aceptadas terminan de servirse (como un kill real).
    `restart()` = vuelve a levantarse en el mismo puerto.
    """

    def __init__(self, port: int, delay_s: float = 0.4):
        self.port = port
        self.delay_s = delay_s
        self.calls = 0
        self.dead = False  # True = proceso muerto: corta llamadas EN VUELO
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.lectura = json.dumps({
            "nif": "", "iban": "", "fecha": "", "total": "",
            "pedido": "", "proveedor": "",
        })

    # -------------------------------------------------- servidor

    def _handler(self):
        stub = self

        class H(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if self.path.startswith("/v1/models"):
                    body = json.dumps({"models": [{"name": "stub-vl"}]}).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_response(404)
                    self.end_headers()

            def do_POST(self) -> None:
                if self.path.startswith("/v1/chat/completions"):
                    length = int(self.headers.get("Content-Length", 0))
                    self.rfile.read(length)
                    stub.calls += 1
                    if stub.delay_s:
                        threading.Event().wait(stub.delay_s)
                    if stub.dead:
                        # kill REAL: la conexión en vuelo se corta sin
                        # respuesta (el cliente ve connection reset)
                        try:
                            self.wfile.close()
                            self.rfile.close()
                        except OSError:
                            pass
                        self.close_connection = True
                        return
                    content = json.dumps({
                        "choices": [{"message": {"content": stub.lectura}}],
                    }).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(content)))
                    self.end_headers()
                    self.wfile.write(content)
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, *args) -> None:  # silencio
                pass

        return H

    def start(self) -> None:
        self._httpd = ThreadingHTTPServer(("127.0.0.1", self.port),
                                          self._handler())
        self._httpd.daemon_threads = True
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.dead = True
        if self._httpd is not None:
            threading.Thread(target=self._httpd.shutdown, daemon=True).start()
            if self._thread is not None:
                self._thread.join(timeout=5)
            self._httpd.server_close()
            self._httpd = None
            self._thread = None

    def restart(self) -> None:
        self.stop()
        self.dead = False
        self.start()


def _hooks_stub(stub: StubLlamaServer) -> DrillHooks:
    url = f"http://127.0.0.1:{stub.port}"

    def health() -> bool:
        return _vlm_up(url, timeout_s=2.0)

    def kill_when() -> bool:
        return stub.calls >= 1  # kill con una llamada rung4 EN VUELO

    def kill(motivo: str) -> dict:
        stub.stop()
        return {"como": f"stub muerto ({motivo})"}

    def restart(_ctx: dict) -> dict:
        stub.restart()
        return {"como": "stub relanzado en el mismo puerto"}

    return DrillHooks(health=health, kill=kill, restart=restart,
                      descripcion="stub llama-server que muere (sin red real)")


def _hooks_stub_con_kill_when(stub: StubLlamaServer) -> DrillHooks:
    h = _hooks_stub(stub)

    return replace(h, descripcion=h.descripcion + " + kill_when")


def _limpiar() -> None:
    if DRILL_TMP.exists():
        shutil.rmtree(DRILL_TMP)
    DRILL_TMP.mkdir(parents=True)


def _pdfs_sandbox(n_scans: int = 2, n_texto: int = 3) -> Path:
    """Directorio con n_scans scans + n_texto facturas de texto (fixtures)."""
    d = DRILL_TMP / "pdfs"
    d.mkdir(parents=True, exist_ok=True)
    for f in sorted((REPO / "tests/fixtures/scans").glob("scan_*.pdf"))[:n_scans]:
        shutil.copy(f, d / f.name)
    for f in sorted((REPO / "tests/fixtures/facturas").glob("*.pdf"))[:n_texto]:
        shutil.copy(f, d / f.name)
    return d


def _cfg(fecha: str = "2026-09-19", **kwargs) -> DrillConfig:
    return DrillConfig(
        facturas_dir=DRILL_TMP / "pdfs",
        store_root=DRILL_TMP / "sandbox",
        fecha_referencia=fecha,
        n_scans=2, n_texto=3, total=5,
        kill_after_files=2,
        kill_timeout_s=12.0,
        timeout_por_archivo_s=20.0,
        vlm_base_url=STUB_URL,
        **kwargs,
    )


def test_stub_llama_server_salud_y_muerte():
    _limpiar()
    stub = StubLlamaServer(STUB_PORT, delay_s=0.05)
    stub.start()
    try:
        assert _vlm_up(STUB_URL, timeout_s=2.0)
        assert stub.calls == 0
    finally:
        stub.stop()
    assert not _vlm_up(STUB_URL, timeout_s=2.0)  # muerto ⇒ health down


def test_drill_stub_kill_degrada_y_recupera_outcomes_identicos():
    """El drill completo con stub: kill a mitad ⇒ degradación medida ⇒
    recuperación (reprocesado dirigido) ⇒ outcomes byte a byte idénticos a
    una corrida sin kill. Sin red real."""
    _limpiar()
    stub = StubLlamaServer(STUB_PORT, delay_s=0.8)
    stub.start()
    try:
        # seleccion: 2 scans (van a rung 4 forzado) + 3 con texto (rung 1)
        _pdfs_sandbox(n_scans=2, n_texto=3)
        cfg = _cfg(kill_when=lambda: stub.calls >= 1)

        resultado = ejecutar_drill(cfg, _hooks_stub(stub))
        assert resultado["hooks"] == _hooks_stub(stub).descripcion
        # degradación medida: al menos 1 archivo con rung 4 skip
        assert len(resultado["degradacion"]["archivos_con_rung4_skip"]) >= 1
        assert resultado["degradacion"]["cola_revision"] >= 1
        # recuperación: outcomes idénticos byte a byte + peldaños iguales
        rec = resultado["recuperacion"]
        assert rec["outcomes_byte_identico_base"] is True
        assert rec["rungs_finales_coinciden"] is True
        assert rec["file_ids_completos"] is True
        # el sandbox separa base del kill: el run base vive en base/store.db,
        # el histórico del kill+recuperado coexiste en kill/store.db
        assert "kill" in rec["runs_en_historico"]
        assert "recuperado" in rec["runs_en_historico"]
        # páginas cuyo rung 4 respondió con proveedor vivo tras recuperar
        assert rec["rung4_llamadas_vivas"] >= 1
        # timeline con el KILL registrado
        assert any(ev["evento"] == "KILL llama-server"
                   for ev in resultado["timeline"])
        # RAM muestreada y bajo control
        ram = resultado["metricas"]["ram"]
        assert ram["muestras"] >= 2
        assert ram["disponible_min_mb"] > 300
        assert ram["rss_proceso_max_mb"] < 2048  # perfil del sistema sano
    finally:
        stub.stop()


def test_drill_sin_kill_igual_al_recuperado():
    """'Sin kill' (corrida base del drill) == corrida con kill tras recuperar:
    mismos resultados (criterio de aceptación)."""
    _limpiar()
    stub = StubLlamaServer(STUB_PORT + 1, delay_s=0.4)
    stub.start()
    try:
        _pdfs_sandbox(n_scans=2, n_texto=3)
        ejecutar_drill(
            _cfg(kill_when=lambda: False),  # el watchdog nunca dispara
            _hooks_stub(stub))
        base_sin_kill = (DRILL_TMP / "sandbox" / "base" / "outcomes.jsonl"
                         ).read_bytes()
        # re-ejecutar el drill completo (kill activo, otra vez)
        _pdfs_sandbox(n_scans=2, n_texto=3)
        cfg2 = _cfg(kill_when=lambda: stub.calls >= 1)
        ejecutar_drill(cfg2, _hooks_stub(stub))
        recuperado = (DRILL_TMP / "sandbox" / "kill" / "outcomes.jsonl"
                      ).read_bytes()
        assert recuperado == base_sin_kill
    finally:
        stub.stop()


def test_drill_store_real_intacto():
    """El drill usa SOLO su sandbox: el store real del lote 1 no se abre."""
    _limpiar()
    store_db = REPO / ".sdd" / "store.db"
    antes = store_db.read_bytes() if store_db.exists() else None
    stub = StubLlamaServer(STUB_PORT + 2, delay_s=0.3)
    stub.start()
    try:
        _pdfs_sandbox()
        ejecutar_drill(_cfg(), _hooks_stub(stub))
    finally:
        stub.stop()
    if antes is not None:
        assert store_db.read_bytes() == antes  # byte a byte intacto
    assert (DRILL_TMP / "sandbox").is_dir()  # todo el estado en el sandbox
