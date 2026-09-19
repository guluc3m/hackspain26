"""Vigilante de carpeta y notificador nativo: fronteras reales, no mocks de navegador.

Se ejercita el módulo real contra PouchDB real (Node) y un servicio de ingestión
falso que respeta el contrato (`submit` durable + `status` por job). Cubre:
estabilidad de ficheros escritos por trozos, entrega exactamente una vez, dedup
por carpeta, reinicio sin reprocesar, bytes cambiados, vigilante deshabilitado,
frontera de notificación ESCALAR, procedencia solo tras entrega real, y la
ausencia de superficie web para el vigilante.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from filemaid.config import AppConfig
from filemaid.desktop.notify import Notificador
from filemaid.desktop.watcher import DEDUP_ID, NOTIFIED_ID, SETTINGS_ID, Watcher
from filemaid.extract.cache import sha256_file
from filemaid.store.pouch import PouchStore, file_key

REPO_ROOT = Path(__file__).resolve().parent.parent
PDF_REAL = REPO_ROOT / "caja-de-alberto" / "facturas" / "2026-07-09_P010.pdf"


class FakeIngesta:
    """Contrato de ingestión: `submit` durable + `status` por job."""

    def __init__(self, resultado: str = "PAGAR", rechazar: bool = False) -> None:
        self.resultado = resultado
        self.rechazar = rechazar
        self.submits: list[dict] = []
        self.intentos = 0
        self._n = 0

    def submit(self, entries, origin: str = "upload") -> dict:
        self.intentos += 1
        if self.rechazar:
            raise ValueError("extensión no soportada")
        self._n += 1
        job_id = f"job-{self._n}"
        aceptados = []
        for rel, abs_ in entries:
            p = Path(abs_)
            sha = sha256_file(p)
            aceptados.append(
                {
                    "file_id": p.name,
                    "file_key": file_key(p.name, sha),
                    "sha256": sha,
                    "rel_path": rel,
                }
            )
        self.submits.append({"job_id": job_id, "entries": list(entries), "origin": origin})
        return {"job_id": job_id, "accepted": aceptados, "rejected": []}

    def status(self, job_id: str) -> dict:
        envio = next(s for s in self.submits if s["job_id"] == job_id)
        items = []
        for rel, abs_ in envio["entries"]:
            p = Path(abs_)
            sha = sha256_file(p)
            items.append(
                {
                    "file_id": p.name,
                    "file_key": file_key(p.name, sha),
                    "sha256": sha,
                    "status": "done",
                    "result": self.resultado,
                    "decision_id": f"decision:{job_id}",
                    "scan_id": job_id,
                    "error": None,
                }
            )
        return {"job_id": job_id, "state": "complete", "items": items}


class FakeNotificador:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok
        self.mensajes: list[tuple[str, str]] = []

    def notificar(self, titulo: str, cuerpo: str) -> bool:
        self.mensajes.append((titulo, cuerpo))
        return self.ok

    def estado(self) -> dict:
        return {"available": self.ok, "detail": ""}


def _watcher(cfg: AppConfig, fake: FakeIngesta, noti=None) -> Watcher:
    """Vigilante sin hilo: se activa por ajustes y se sondea con `escanear()`."""
    return Watcher(
        cfg,
        noti or FakeNotificador(),
        servicio=fake,
        poll_s=3600.0,
        settle_polls=2,
        reconcile_s=0.0,
    )


def _activar(cfg: AppConfig, carpeta: Path, enabled: bool = True) -> None:
    PouchStore(cfg.root).local_put(SETTINGS_ID, {"folder": str(carpeta), "enabled": enabled})


def _carpeta(tmp_path: Path, nombre: str = "vigilada") -> Path:
    carpeta = tmp_path / nombre
    carpeta.mkdir()
    return carpeta


def test_fichero_por_trozos_estable_entrega_exactamente_una_vez(tmp_path, cfg):
    carpeta = _carpeta(tmp_path)
    destino = carpeta / "factura.pdf"
    datos = PDF_REAL.read_bytes()
    mitad = len(datos) // 2
    fake = FakeIngesta()
    _activar(cfg, carpeta)
    watcher = _watcher(cfg, fake)

    with destino.open("wb") as f:
        f.write(datos[:mitad])
        f.flush()
        watcher.escanear()  # parcial: cuenta 1, no entrega
        assert fake.submits == []
        f.write(datos[mitad:])

    watcher.escanear()  # firma nueva: cuenta 1
    assert fake.submits == []
    watcher.escanear()  # estable: entrega
    assert len(fake.submits) == 1
    assert fake.submits[0]["origin"] == "watcher"
    assert fake.submits[0]["entries"] == [("factura.pdf", str(destino))]

    for _ in range(3):
        watcher.escanear()
    assert len(fake.submits) == 1  # dedup: no reprocesa lo entregado


def test_reinicio_sin_cambios_no_reprocesa(tmp_path, cfg):
    carpeta = _carpeta(tmp_path)
    shutil.copyfile(PDF_REAL, carpeta / "factura.pdf")
    fake = FakeIngesta()
    _activar(cfg, carpeta)

    primero = _watcher(cfg, fake)
    for _ in range(3):
        primero.escanear()
    assert len(fake.submits) == 1

    reinicio = _watcher(cfg, fake)  # recarga ajustes y dedup del disco
    for _ in range(3):
        reinicio.escanear()
    assert len(fake.submits) == 1


def test_bytes_cambiados_reprocesa(tmp_path, cfg):
    carpeta = _carpeta(tmp_path)
    destino = carpeta / "factura.pdf"
    shutil.copyfile(PDF_REAL, destino)
    fake = FakeIngesta()
    _activar(cfg, carpeta)
    watcher = _watcher(cfg, fake)
    for _ in range(3):
        watcher.escanear()
    assert len(fake.submits) == 1

    destino.write_bytes(PDF_REAL.read_bytes() + b"\n% cambio")
    for _ in range(3):
        watcher.escanear()
    assert len(fake.submits) == 2


def test_vigilante_deshabilitado_no_procesa(tmp_path, cfg):
    carpeta = _carpeta(tmp_path)
    shutil.copyfile(PDF_REAL, carpeta / "factura.pdf")
    fake = FakeIngesta()
    _activar(cfg, carpeta, enabled=False)
    watcher = _watcher(cfg, fake)
    for _ in range(3):
        watcher.escanear()
    assert fake.submits == []
    assert watcher.estado()["enabled"] is False


def test_ignora_temporales_symlinks_y_no_pdf(tmp_path, cfg):
    carpeta = _carpeta(tmp_path)
    shutil.copyfile(PDF_REAL, carpeta / "factura.pdf")
    (carpeta / "factura.pdf.tmp").write_bytes(PDF_REAL.read_bytes())
    (carpeta / "~$factura.pdf").write_bytes(PDF_REAL.read_bytes())
    (carpeta / ".oculto.pdf").write_bytes(PDF_REAL.read_bytes())
    (carpeta / "notas.txt").write_text("no es una factura")
    (carpeta / "sub").mkdir()
    shutil.copyfile(PDF_REAL, carpeta / "sub" / "anidada.pdf")
    fuera = tmp_path / "fuera.pdf"
    shutil.copyfile(PDF_REAL, fuera)
    (carpeta / "enlace.pdf").symlink_to(fuera)

    fake = FakeIngesta()
    _activar(cfg, carpeta)
    watcher = _watcher(cfg, fake)
    for _ in range(3):
        watcher.escanear()
    assert [s["entries"][0][0] for s in fake.submits] == ["factura.pdf"]


def test_dedup_por_carpeta_no_omite_mismo_nombre(tmp_path, cfg):
    primera = _carpeta(tmp_path, "primera")
    segunda = _carpeta(tmp_path, "segunda")
    shutil.copyfile(PDF_REAL, primera / "factura.pdf")
    shutil.copyfile(PDF_REAL, segunda / "factura.pdf")
    fake = FakeIngesta()

    _activar(cfg, primera)
    watcher = _watcher(cfg, fake)
    for _ in range(3):
        watcher.escanear()
    assert len(fake.submits) == 1

    _activar(cfg, segunda)
    otro = _watcher(cfg, fake)
    for _ in range(3):
        otro.escanear()
    assert len(fake.submits) == 2  # mismo nombre base, otra carpeta: no se omite


def test_notificacion_solo_escalar_y_una_vez(tmp_path, cfg):
    carpeta = _carpeta(tmp_path)
    shutil.copyfile(PDF_REAL, carpeta / "factura.pdf")
    fake = FakeIngesta(resultado="ESCALAR")
    noti = FakeNotificador()
    _activar(cfg, carpeta)
    watcher = _watcher(cfg, fake, noti)
    for _ in range(3):
        watcher.escanear()
    assert len(noti.mensajes) == 1
    assert "ESCALAR" in noti.mensajes[0][1]

    reinicio = _watcher(cfg, fake, noti)
    for _ in range(3):
        reinicio.escanear()
    assert len(noti.mensajes) == 1  # procedencia: no repite en reinicio


def test_pagar_no_notifica(tmp_path, cfg):
    carpeta = _carpeta(tmp_path)
    shutil.copyfile(PDF_REAL, carpeta / "factura.pdf")
    fake = FakeIngesta(resultado="PAGAR")
    noti = FakeNotificador()
    _activar(cfg, carpeta)
    watcher = _watcher(cfg, fake, noti)
    for _ in range(3):
        watcher.escanear()
    assert noti.mensajes == []


def test_reconciliacion_por_db_notifica_escalar_una_vez(tmp_path, cfg):
    """Un job completado con la app cerrada se notifica al reiniciar, una sola vez."""
    carpeta = _carpeta(tmp_path)
    destino = carpeta / "factura.pdf"
    shutil.copyfile(PDF_REAL, destino)
    store = PouchStore(cfg.root)
    sha = sha256_file(destino)
    clave = f'["{carpeta}", "factura.pdf"]'
    store.local_put(SETTINGS_ID, {"folder": str(carpeta), "enabled": True})
    store.local_put(DEDUP_ID, {clave: sha})
    store.put(
        {
            "_id": "decision:scan-1",
            "kind": "decision",
            "file_id": "factura.pdf",
            "file_key": file_key("factura.pdf", sha),
            "scan_id": "scan-1",
            "timestamp": 1.0,
            "decision": {"result": "ESCALAR"},
        }
    )
    noti = FakeNotificador()
    watcher = _watcher(cfg, FakeIngesta(), noti)
    watcher.escanear()
    assert len(noti.mensajes) == 1
    watcher.escanear()
    assert len(noti.mensajes) == 1


def test_procedencia_solo_tras_entrega_nativa(tmp_path, cfg):
    carpeta = _carpeta(tmp_path)
    shutil.copyfile(PDF_REAL, carpeta / "factura.pdf")
    fake = FakeIngesta(resultado="ESCALAR")
    noti = FakeNotificador(ok=False)
    _activar(cfg, carpeta)
    watcher = _watcher(cfg, fake, noti)
    for _ in range(3):
        watcher.escanear()
    assert len(noti.mensajes) == 1  # se intentó
    assert not PouchStore(cfg.root).local_get(NOTIFIED_ID)  # no se publicó procedencia
    assert "notificación" in watcher.estado()["error"]


def test_pdf_truncado_no_se_encola_y_se_reintenta_al_completarse(tmp_path, cfg):
    carpeta = _carpeta(tmp_path)
    destino = carpeta / "factura.pdf"
    datos = PDF_REAL.read_bytes()
    fake = FakeIngesta()
    _activar(cfg, carpeta)
    watcher = _watcher(cfg, fake)

    destino.write_bytes(datos[: len(datos) // 2])  # sin tráiler %%EOF
    for _ in range(3):
        watcher.escanear()
    assert fake.submits == []

    destino.write_bytes(datos)  # copia completada
    for _ in range(3):
        watcher.escanear()
    assert len(fake.submits) == 1


def test_rechazo_no_marca_dedup_y_reintenta_al_cambiar(tmp_path, cfg):
    carpeta = _carpeta(tmp_path)
    destino = carpeta / "factura.pdf"
    shutil.copyfile(PDF_REAL, destino)
    fake = FakeIngesta(rechazar=True)
    _activar(cfg, carpeta)
    watcher = _watcher(cfg, fake)
    for _ in range(3):
        watcher.escanear()
    assert fake.intentos == 1
    assert not PouchStore(cfg.root).local_get(DEDUP_ID)  # sin dedup permanente

    fake.rechazar = False
    destino.write_bytes(PDF_REAL.read_bytes() + b"\n% cambio")
    for _ in range(3):
        watcher.escanear()
    assert len(fake.submits) == 1


def test_configurar_valida_carpeta_y_persiste(tmp_path, cfg):
    watcher = _watcher(cfg, FakeIngesta())
    with pytest.raises(ValueError):
        watcher.configurar(str(tmp_path / "no-existe"), True)

    carpeta = _carpeta(tmp_path)
    estado = watcher.configurar(str(carpeta), True)
    assert estado["enabled"] is True
    assert estado["folder"] == str(carpeta.resolve())
    assert PouchStore(cfg.root).local_get(SETTINGS_ID) == {
        "folder": str(carpeta.resolve()),
        "enabled": True,
    }
    watcher.stop()


def test_stop_impide_nuevos_envios(tmp_path, cfg):
    carpeta = _carpeta(tmp_path)
    shutil.copyfile(PDF_REAL, carpeta / "factura.pdf")
    fake = FakeIngesta()
    _activar(cfg, carpeta)
    watcher = _watcher(cfg, fake)
    watcher.stop()
    for _ in range(3):
        watcher.escanear()
    assert fake.submits == []


def test_web_no_expone_vigilancia_ni_navegador_de_ficheros(cfg):
    from filemaid.api.app import create_app

    app = create_app(cfg)
    rutas = {getattr(r, "path", "") for r in app.routes}
    prohibidas = ("vigil", "watch", "carpeta", "folder", "files", "browse", "fs")
    assert not [p for p in rutas if any(t in p.lower() for t in prohibidas)]


def test_notificador_sin_qt_degrada(monkeypatch):
    monkeypatch.setitem(sys.modules, "qtpy", None)
    noti = Notificador()
    noti.preparar()
    assert noti.estado()["available"] is False
    assert noti.notificar("t", "c") is False
