"""T40F1 — Higiene de secretos como test PERMANENTE.

AGENTS.md §13: ninguna API key, token ni credencial en este repo; las claves
viven solo en /home/deploy/.nanobot/*.json. Hasta hoy eso era un ritual manual
(grep antes de cada commit): un solo olvido mete una credencial en el
histórico público y no tiene marcha atrás. Este test corre en CADA pytest y
rompe la build si algo con forma de credencial entra en el working tree.

Qué escanea: los ficheros que viajarían en un commit
(`git ls-files --cached --others --exclude-standard` = tracked + untracked
no ignorados). Binarios excluidos.

Patrones de SEÑAL ALTA (formas reales de credencial). Deliberadamente NO
casan con menciones documentales del repo («apiKey» a secas, «sk-[A-Za-z0-9]»
en la doctrina, el decoy `apiKey=hola` del test de staging): una credencial
real es una clave LARGA asignada a un valor.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

TAM_MAX_BYTES = 2_000_000  # guardia: los PDFs/xlsx del corpus no se leen

# (etiqueta, regex). Señal alta: sin falsos positivos documentales.
PATRONES: list[tuple[str, re.Pattern[str]]] = [
    ("clave estilo OpenAI/DeepSeek (sk- larga)",
     re.compile(r"sk-[A-Za-z0-9]{16,}")),
    ("apiKey asignada a un valor plausible",
     re.compile(r"""apiKey["']?\s*[:=]\s*["']?[A-Za-z0-9_\-]{8,}""")),
    ("AccessKeyId de AWS (AKIA)",
     re.compile(r"AKIA[0-9A-Z]{16}")),
    ("token clasico de GitHub (ghp_)",
     re.compile(r"ghp_[A-Za-z0-9]{30,}")),
    ("token fino de GitHub (github_pat_)",
     re.compile(r"github_pat_[A-Za-z0-9_]{40,}")),
    ("token de Slack (xox*-)",
     re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
    ("clave privada embebida",
     re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
]

# Ficheros con forma de secreto A PROPÓSITO (decoys verificados por tests de
# la propia higiene). Cada entrada lleva su justificación. Vacío hoy: los
# patrones son de señal alta y el repo no lo necesita.
PERMITIDOS: dict[str, str] = {}


def _ficheros_del_commit() -> list[Path]:
    """Ficheros tracked + untracked-no-ignorados: lo que un commit llevaría."""
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard",
         "-z"],
        cwd=REPO, capture_output=True, check=True,
    )
    rutas = [Path(p) for p in out.stdout.decode("utf-8").split("\0") if p]
    return [REPO / r for r in rutas]


def _texto_si_es_texto(ruta: Path) -> str | None:
    """Contenido como texto, o None si es binario/demasiado grande."""
    try:
        bruto = ruta.read_bytes()
    except OSError:
        return None
    if len(bruto) > TAM_MAX_BYTES or b"\x00" in bruto:
        return None
    return bruto.decode("utf-8", errors="replace")


def _clave(ruta: Path) -> str:
    """Clave estable del fichero para PERMITIDOS (ruta relativa al repo)."""
    return ruta.relative_to(REPO).as_posix() if ruta.is_relative_to(REPO) \
        else str(ruta)


def _hallazgos(rutas: list[Path]) -> list[str]:
    """Devuelve una línea descriptiva por cada patrón casado."""
    encontrados: list[str] = []
    for ruta in rutas:
        rel = _clave(ruta)
        if rel in PERMITIDOS:
            continue
        texto = _texto_si_es_texto(ruta)
        if texto is None:
            continue
        for n_linea, linea in enumerate(texto.splitlines(), start=1):
            for etiqueta, patron in PATRONES:
                m = patron.search(linea)
                if m:
                    fragmento = linea.strip()
                    if len(fragmento) > 120:
                        fragmento = fragmento[:117] + "..."
                    encontrados.append(
                        f"{rel}:{n_linea} — {etiqueta}: {fragmento}")
    return encontrados


def _escanear_repo() -> list[str]:
    return _hallazgos(_ficheros_del_commit())


# ------------------------------------------------------------------ tests


def test_repo_sin_secretos():
    """El requisito no negociable de AGENTS.md §13, verificado en cada pytest."""
    hallados = _escanear_repo()
    assert hallados == [], (
        "Posible credencial en el repo (AGENTS.md §13). Revisa cada línea, "
        "elimínala o justifícala en PERMITIDOS:\n" + "\n".join(hallados)
    )


def test_el_detector_detecta_un_secreto_plantado(tmp_path):
    """Self-test del detector: payload SIMULADO construido en runtime
    (así el fuente de este test no contiene ninguna forma de credencial).
    El fichero plantado vive en tmp_path, NO en el repo."""
    clave = "sk-" + "a1" * 12          # sk- + 24 alfanuméricos
    otra = "apiKey = " + "x" * 12
    objetivo = tmp_path / "con-secreto.txt"
    objetivo.write_text(f"config:\n  token: {clave}\n  {otra}\n",
                        encoding="utf-8")
    limpio = tmp_path / "limpio.txt"
    limpio.write_text("apiKey sin valor ni asignación; sk- corto: sk-abc\n",
                      encoding="utf-8")

    hallados = _hallazgos([objetivo, limpio])

    assert len(hallados) == 2, hallados
    assert any("con-secreto.txt:2" in h for h in hallados)
    assert any("con-secreto.txt:3" in h for h in hallados)
    # y el permitido se respeta si se declara con su porqué
    PERMITIDOS[_clave(objetivo)] = "prueba del detector"
    try:
        assert _hallazgos([objetivo]) == []
    finally:
        PERMITIDOS.pop("con-secreto.txt", None)