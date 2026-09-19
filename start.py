#!/usr/bin/env python3
"""Lanzador de filemaid: prepara el entorno y arranca cliente o servidor.

Uso:
    python start.py [client|server] [opciones]

`client` (por defecto) prepara el entorno uv (Python 3.13), las dependencias
Node de PouchDB y el build de producción de la UI, y abre la app de escritorio
(ventana nativa o `--headless`). `server` solo se admite en Linux y delega en
`filemaid server`, que aprovisiona el VLM local en el propio proceso servidor.

Este lanzador no guarda estado propio: el modo (standalone/servidor) se
persiste con la API existente (`RuntimeSettings` sobre PouchDB). Solo usa
stdlib, para poder ejecutarse con el Python del sistema antes de crear el
entorno del proyecto.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
POUCHDB_DIR = REPO_ROOT / "src" / "filemaid" / "store" / "pouchdb"
FRONTEND_DIR = REPO_ROOT / "frontend"
DIST_INDEX = FRONTEND_DIR / "dist" / "index.html"

MIN_NODE_MAJOR = 20
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
_IS_WINDOWS = os.name == "nt"


def _log(message: str) -> None:
    print(f"[filemaid] {message}", file=sys.stderr)


def _resolve(name: str) -> str:
    """Ruta absoluta del ejecutable `name`, o error claro si falta."""
    found = shutil.which(name)
    if found is None:
        raise SystemExit(
            f"[filemaid] falta '{name}' en PATH. Instálalo y vuelve a intentarlo "
            "(uv: https://docs.astral.sh/uv/ · Node >= 20: https://nodejs.org/)"
        )
    return found


def _npm_cli_path(exe: str, name: str) -> Path | None:
    """Localiza `<name>-cli.js` junto al ejecutable de Node (layout oficial)."""
    base = Path(exe).resolve().parent
    for candidate in (
        base / "node_modules" / "npm" / "bin" / f"{name}-cli.js",
        base / ".." / "lib" / "node_modules" / "npm" / "bin" / f"{name}-cli.js",
    ):
        if candidate.is_file():
            return candidate
    return None


def _node_cli(name: str, *args: str) -> list[str]:
    """Invoca un CLI de npm (npm/npx) sin shell.

    En POSIX se ejecuta el binario directamente. En Windows se ejecuta
    `node <name>-cli.js` (layout oficial de Node); si no se localiza, falla con
    un error accionable en vez de recurrir a cmd.exe (evita comportamiento de
    shell oculto con rutas/argumentos controlados por el usuario).
    """
    exe = _resolve(name)
    if not _IS_WINDOWS:
        return [exe, *args]
    node = shutil.which("node")
    if node is None:
        raise SystemExit(
            "[filemaid] Node no encontrado en PATH; se requiere Node >= 20 (https://nodejs.org/)"
        )
    cli = _npm_cli_path(exe, name)
    if cli is None:
        raise SystemExit(
            f"[filemaid] no se encontró {name}-cli.js junto a {exe}. "
            "Instala Node >= 20 desde https://nodejs.org/ (distribución oficial)."
        )
    return [node, str(cli), *args]


def _run(cmd: list[str], *, env: dict[str, str] | None = None, cwd: Path = REPO_ROOT) -> None:
    _log("$ " + " ".join(str(part) for part in cmd))
    try:
        subprocess.run(cmd, cwd=str(cwd), env=env, check=True)
    except FileNotFoundError as exc:
        raise SystemExit(f"[filemaid] no se pudo ejecutar {cmd[0]}: {exc}") from exc
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            f"[filemaid] falló: {' '.join(str(part) for part in cmd)} (exit {exc.returncode})"
        ) from exc


def _uv() -> str:
    return _resolve("uv")


def _check_node() -> None:
    node = _resolve("node")
    try:
        raw = subprocess.run(
            [node, "--version"], capture_output=True, text=True, check=True
        ).stdout.strip()
        major = int(raw.lstrip("v").split(".")[0])
    except (subprocess.CalledProcessError, ValueError) as exc:
        raise SystemExit(f"[filemaid] no se pudo determinar la versión de Node: {exc}") from exc
    if major < MIN_NODE_MAJOR:
        raise SystemExit(f"[filemaid] se requiere Node >= {MIN_NODE_MAJOR} (encontrado {raw})")


def _uv_sync(extra_desktop: bool) -> None:
    """Sincroniza el entorno sin eliminar extras ajenos (--inexact)."""
    cmd = [_uv(), "sync", "--inexact"]
    if extra_desktop:
        cmd += ["--extra", "desktop"]
    _run(cmd)


def _uv_run(
    args: list[str],
    *,
    extra_desktop: bool = False,
    sync: bool = True,
    env: dict[str, str] | None = None,
) -> None:
    """Ejecuta dentro del entorno uv preservando paquetes ajenos."""
    cmd = [_uv(), "run"]
    if sync:
        cmd += ["--inexact"]
        if extra_desktop:
            cmd += ["--extra", "desktop"]
    else:
        cmd += ["--no-sync"]
    cmd += args
    _run(cmd, env=env)


def _pouchdb_installed() -> bool:
    return (POUCHDB_DIR / "node_modules" / "pouchdb" / "package.json").is_file()


def _smoke_pouchdb() -> None:
    """Comprueba que `pouchdb` se importa; no abre ni muta ninguna base."""
    node = _resolve("node")
    code = (
        "import('pouchdb').then(m => { if (typeof (m.default || m) !== 'function') "
        "process.exit(1); }).catch(e => { console.error(e); process.exit(1); })"
    )
    _run([node, "-e", code], cwd=POUCHDB_DIR)


def _ensure_pouchdb() -> None:
    """Node >= 20 siempre; instala las deps si faltan y verifica el import."""
    _check_node()
    if not _pouchdb_installed():
        _run(_node_cli("npm", "ci"), cwd=POUCHDB_DIR)
    if not _pouchdb_installed():
        raise SystemExit("[filemaid] PouchDB no quedó instalado en src/filemaid/store/pouchdb")
    _smoke_pouchdb()


def _frontend_inputs():
    for base in (FRONTEND_DIR / "src", FRONTEND_DIR / "public"):
        if base.is_dir():
            yield from (path for path in base.rglob("*") if path.is_file())
    for name in ("index.html", "package.json", "pnpm-lock.yaml", "vite.config.ts", "tsconfig.json"):
        path = FRONTEND_DIR / name
        if path.is_file():
            yield path


def _ui_build_needed() -> bool:
    """Rebuild solo si falta el build o hay fuentes más nuevas (sin recompilar a ciegas)."""
    if not DIST_INDEX.is_file():
        return True
    built = DIST_INDEX.stat().st_mtime
    return any(path.stat().st_mtime > built for path in _frontend_inputs())


def _ensure_ui() -> None:
    if not _ui_build_needed():
        _log("UI ya construida y al día; se omite el build")
        return
    _check_node()
    _run(
        _node_cli(
            "npx", "--yes", "pnpm", "--dir", str(FRONTEND_DIR), "install", "--frozen-lockfile"
        )
    )
    _run(_node_cli("npx", "--yes", "pnpm", "--dir", str(FRONTEND_DIR), "build"))


def _persist_standalone() -> None:
    """Guarda modo standalone con la API existente; el proceso de la app aprovisiona."""
    code = (
        "from filemaid.config import AppConfig\n"
        "from filemaid.runtime import RuntimeSettings\n"
        "RuntimeSettings(AppConfig.load()).save({'mode': 'standalone'})\n"
    )
    _uv_run(["python", "-c", code], sync=False)


def _warn_qt_platform() -> None:
    """Aviso (sin tocar el entorno) si QT_QPA_PLATFORM es una lista de respaldo."""
    if sys.platform != "linux":
        return
    platform = os.environ.get("QT_QPA_PLATFORM", "")
    if ";" in platform:
        _log(
            f"aviso: QT_QPA_PLATFORM='{platform}' es una lista de respaldo y la ventana QT "
            "puede cerrarse al instante. Lanza con una sola plataforma, p. ej. "
            "QT_QPA_PLATFORM=wayland python start.py client"
        )


def _client(args: argparse.Namespace) -> int:
    native = not args.headless
    _uv_sync(extra_desktop=native)
    _ensure_pouchdb()
    _ensure_ui()
    env = dict(os.environ)
    if args.ui_url:
        env["FILEMAID_UI_URL"] = args.ui_url
    if args.standalone:
        _persist_standalone()
    if native:
        _warn_qt_platform()
    cmd = ["filemaid-desktop"]
    if args.headless:
        cmd += ["--headless", "--port", str(args.port)]
    _uv_run(cmd, extra_desktop=native, env=env)
    return 0


def _server(args: argparse.Namespace) -> int:
    # Guardas antes de cualquier efecto secundario (sync, descargas, builds).
    if sys.platform != "linux":
        raise SystemExit("[filemaid] el modo servidor solo está soportado en Linux")
    if args.host not in LOOPBACK_HOSTS and not os.environ.get("FILEMAID_SERVER_TOKEN"):
        raise SystemExit(
            "[filemaid] FILEMAID_SERVER_TOKEN es requerido cuando --host no es loopback"
        )
    _uv_sync(extra_desktop=False)
    _ensure_pouchdb()
    _uv_run(["filemaid", "server", "--host", args.host, "--port", str(args.port)])
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="start.py",
        description="Prepara el entorno y arranca filemaid (cliente por defecto, o servidor).",
    )
    sub = parser.add_subparsers(dest="mode")

    p_client = sub.add_parser("client", help="app de escritorio (ventana nativa o --headless)")
    p_client.add_argument(
        "--headless",
        action="store_true",
        help="sirve la UI y la API en loopback sin abrir ventana",
    )
    p_client.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("FILEMAID_PORT", "8000")),
        help="puerto loopback en modo headless (por defecto FILEMAID_PORT o 8000)",
    )
    p_client.add_argument(
        "--standalone",
        action="store_true",
        help="persiste el modo standalone y deja que la app aprovisione el VLM local",
    )
    p_client.add_argument(
        "--ui-url",
        default="",
        help="URL de UI en desarrollo (FILEMAID_UI_URL); por defecto usa el build",
    )

    p_server = sub.add_parser("server", help="servidor VLM local (solo Linux)")
    p_server.add_argument("--host", default="127.0.0.1", help="host del servidor")
    p_server.add_argument("--port", type=int, default=8001, help="puerto del servidor")

    raw = list(sys.argv[1:] if argv is None else argv)
    if raw and raw[0] in {"-h", "--help"}:
        parser.print_help()
        return 0
    if not raw or raw[0].startswith("-"):
        raw = ["client", *raw]
    args = parser.parse_args(raw)

    if args.mode == "server":
        return _server(args)
    return _client(args)


if __name__ == "__main__":
    raise SystemExit(main())
