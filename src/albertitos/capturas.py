"""Capturas reales de la app para el anuncio Remotion (T36).

`uv run python -m albertitos.capturas` — arranca la UI contra el store REAL
(solo lectura), captura las pantallas con el Chrome Headless Shell que
Remotion ya descargó (sin Playwright ni otro navegador) y las deja en
`presentation/public/capturas/` (gitignored). La captura de la pantalla de
Resumen usa el HTML generado por T30 (€ en riesgo).
"""

from __future__ import annotations

import time
from pathlib import Path

from albertitos.desktop import _store_dir, apagar, arrancar_servidor

DESTINO_DEFECTO = Path("presentation/public/capturas")
RESUMEN = DESTINO_DEFECTO / "resumen_alberto.html"
SHELL = Path(
    "presentation/node_modules/.remotion/chrome-headless-shell/linux64/"
    "chrome-headless-shell-linux64/chrome-headless-shell"
)


def pantallas(base_url: str) -> list[tuple[str, str]]:
    """(nombre, url) — las 5 pantallas de la app contra el store real."""
    return [
        ("facturas", f"{base_url}/facturas?result=ESCALAR"),
        ("revision", f"{base_url}/revision"),
        ("reglas", f"{base_url}/reglas"),
        ("salud", f"{base_url}/salud"),
        ("operaciones", f"{base_url}/"),
    ]


def capturar(destino: Path | None = None,
             shell: Path | None = None) -> list[Path]:
    """Captura las pantallas reales. Devuelve las rutas capturadas."""
    destino = destino or DESTINO_DEFECTO
    shell = shell or SHELL
    destino.mkdir(parents=True, exist_ok=True)
    if not shell.exists():
        print(f"aviso: {shell} no existe — corre el render de Remotion "
              "una vez para descargar el Chrome Headless Shell")
        return []

    from playwright.sync_api import sync_playwright

    capturadas: list[Path] = []
    server, base_url = arrancar_servidor(_store_dir())
    try:
        time.sleep(0.5)  # la UI renderiza sus datos en el primer golpe
        with sync_playwright() as pw:
            # el shell headless de Remotion sirve como chromium (sin otra descarga)
            navegador = pw.chromium.launch(
                executable_path=str(shell), args=["--no-sandbox"])
            pagina = navegador.new_page(viewport={"width": 1600, "height": 1000})
            objetivos = pantallas(base_url)
            if RESUMEN.exists():
                objetivos.insert(0, ("inicio", RESUMEN.resolve().as_uri()))
            # Revisión CON imágenes reales: el sandbox del drill EN VIVO (T24)
            # conserva la cola con la página rasterizada de cada degradado.
            store_drill = Path(".sdd/drill-live/kill")
            rq_ledger = store_drill / "ledger" / "review-queue"
            if (store_drill / "review-queue" / "review.jsonl").exists() \
                    and not rq_ledger.is_dir():
                # la UI lee el review-queue HERMANO del ledger (contrato T5):
                # el sandbox del drill lo deja junto al store — symlink
                try:
                    rq_ledger.symlink_to(store_drill / "review-queue",
                                         target_is_directory=True)
                except FileExistsError:
                    pass
            if (store_drill / "review-queue" / "review.jsonl").exists():
                from albertitos.desktop import apagar as _ap

                _server_d, base_d = arrancar_servidor(store_drill / "ledger")
                objetivos = [(n, u) for n, u in objetivos if n != "revision"]
                objetivos.append(("revision", f"{base_d}/revision"))
                _ = _ap  # el segundo server se apaga en el finally externo
                time.sleep(0.4)
            for nombre, url in objetivos:
                salida = destino / f"{nombre}.png"
                try:
                    pagina.goto(url, wait_until="domcontentloaded", timeout=15000)
                    pagina.wait_for_timeout(800)  # HTMX pinta sus datos
                    pagina.screenshot(path=str(salida))
                    capturadas.append(salida)
                except Exception as e:  # noqa: BLE001 — una pantalla sin captura no aborta
                    print(f"aviso: {nombre} sin captura: {str(e)[:160]}")
            navegador.close()
    finally:
        apagar(server)
        try:
            apagar(_server_d)
        except (NameError, UnboundLocalError):
            pass
    return capturadas


def main() -> int:
    capturadas = capturar()
    for p in capturadas:
        print(f"captura: {p}")
    print(f"total: {len(capturadas)}")
    return 0 if capturadas else 1


if __name__ == "__main__":
    raise SystemExit(main())