#!/usr/bin/env python3
"""Genera la voz narrada del vídeo (esc1..esc8) con piper.

Los textos salen de `guion_tts.md` (fuente de verdad narrativa: este script no
los reescribe). Cada toma debe **llenar** su escena:

    presupuesto = frames/30 − VOZ_delay ;  holgura = presupuesto − toma

Holgura objetivo 0,8–1,5 s; nunca >2,0 s (aire muerto) ni <0,5 s (límite duro).

Medido: con la prosodia del modelo, la duración de piper es **estocástica**
(desviación ≈0,57 s por toma) y `--length-scale` apenas manda (≈+2,5 % de 0,90 a
1,12; sublineal fuera de ese rango). Por eso el script **mide la toma real** y
repite la síntesis hasta que cae en el objetivo: `--length-scale` se ajusta como
mando fino y el reparto real lo decide la longitud del texto.

Escribe `video/narracion/escN.wav` y su copia byte-idéntica en
`video/public/narracion/escN.wav` (la que sirve `staticFile`).

Uso:
    python3 narracion/gen_tts.py                 # regenera las 8 tomas
    python3 narracion/gen_tts.py --only 3,5,7    # solo algunas escenas
    python3 narracion/gen_tts.py --dry-run       # sintetiza y mide, no escribe
    python3 narracion/gen_tts.py --measure       # media/sd por escena (calibrar texto)
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

VIDEO = Path(__file__).resolve().parents[1]
REPO = VIDEO.parent
GUION = VIDEO / "narracion" / "guion_tts.md"
NARR = VIDEO / "narracion"
PUBLIC = VIDEO / "public" / "narracion"
DEFAULT_MODEL = REPO / "models" / "tts" / "es_ES-carlfm-x_low.onnx"

FPS = 30
SCENE_IDS = ["portada", "problema", "producto", "escalera", "traza", "adrs", "resiliencia", "escala"]
FRAMES = [360, 690, 600, 900, 1050, 600, 600, 600]
VOZ_FRAMES = [30, 30, 36, 60, 75, 45, 30, 30]

SLACK_MIN = 0.8       # objetivo
SLACK_MAX = 1.5       # objetivo
SLACK_HARD = 0.5      # límite duro (nunca menos)
SLACK_AIR = 2.0       # aire muerto (nunca más)
SLACK_TARGET = (SLACK_MIN + SLACK_MAX) / 2
LS_MIN, LS_MAX, LS_STEP = 0.90, 1.12, 0.02

HEADER = re.compile(r"^\*\*esc(\d+) \(([^)]*)\):\*\*\s*$")


def parse_texts() -> dict[int, str]:
    """Extrae los textos de `guion_tts.md` (bloques `**escN (...):**`)."""
    texts: dict[int, str] = {}
    current: int | None = None
    buf: list[str] = []
    for raw in GUION.read_text(encoding="utf-8").splitlines():
        m = HEADER.match(raw.strip())
        if m:
            if current is not None and buf:
                texts[current] = re.sub(r"\s+", " ", " ".join(buf)).strip()
            current, buf = int(m.group(1)), []
            continue
        if current is None:
            continue
        line = raw.strip()
        if not line:
            if buf:
                texts[current] = re.sub(r"\s+", " ", " ".join(buf)).strip()
                current, buf = None, []
            continue
        buf.append(line)
    if current is not None and buf:
        texts[current] = re.sub(r"\s+", " ", " ".join(buf)).strip()
    return texts


def wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as wf:
        return wf.getnframes() / wf.getframerate()


class Synth:
    """Envuelve el CLI de piper: sintetiza a wav temporal y mide la duración."""

    def __init__(self, piper: str, model: Path, tmpdir: Path):
        self.piper = piper
        self.model = model
        self.tmpdir = tmpdir
        self.rolls = 0

    def roll(self, idx: int, text: str, ls: float) -> tuple[float, Path]:
        self.rolls += 1
        out = self.tmpdir / f"esc{idx + 1}-ls{ls:.2f}-r{self.rolls}.wav"
        cmd = [self.piper, "-m", str(self.model), "-f", str(out), "--length-scale", f"{ls:.4f}"]
        res = subprocess.run(cmd, input=text.encode("utf-8"), capture_output=True)
        if res.returncode != 0:
            raise SystemExit(f"piper falló (esc{idx + 1}, ls={ls}):\n{res.stderr.decode('utf-8', 'replace')}")
        return wav_seconds(out), out


def fit(synth: Synth, idx: int, text: str, budget: float, rolls_max: int):
    """Sintetiza hasta que la toma medida cae en la ventana de holgura."""
    ls = 1.0
    attempts: list[tuple[float, float, float]] = []
    best = None  # (error vs objetivo, ls, dur, path, slack, dentro de la ventana)
    for _ in range(rolls_max):
        dur, path = synth.roll(idx, text, ls)
        slack = budget - dur
        attempts.append((ls, dur, slack))
        in_window = SLACK_MIN <= slack <= SLACK_MAX
        ok_hard = SLACK_HARD <= slack <= SLACK_AIR
        cand = (abs(slack - SLACK_TARGET), ls, dur, path, slack, in_window)
        if (in_window or ok_hard) and (best is None or cand[0] < best[0]):
            best = cand
        if in_window:
            return ls, dur, path, slack, "OK", attempts
        mean_slack = statistics.fmean(a[2] for a in attempts)
        if mean_slack > SLACK_MAX and ls < LS_MAX:
            ls = min(LS_MAX, ls + LS_STEP)
        elif mean_slack < SLACK_MIN and ls > LS_MIN:
            ls = max(LS_MIN, ls - LS_STEP)

    if best is not None:
        _, ls, dur, path, slack, _ = best
        return ls, dur, path, slack, "WARN", attempts

    mean_slack = statistics.fmean(a[2] for a in attempts)
    hint = "más largo" if mean_slack > SLACK_MAX else "más corto"
    raise SystemExit(
        f"esc{idx + 1}: no hay toma válida en {rolls_max} intentos (holgura media {mean_slack:+.3f} s, "
        f"límites {SLACK_HARD}–{SLACK_AIR} s) — el texto debe ser {hint}"
    )


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def budgets() -> list[float]:
    return [FRAMES[i] / FPS - VOZ_FRAMES[i] / FPS for i in range(8)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="índices 1..8 separados por comas (por defecto: todas)")
    ap.add_argument("--dry-run", action="store_true", help="sintetiza y mide, pero no escribe wavs")
    ap.add_argument("--measure", action="store_true", help="solo calibración: media/sd de cada texto a --ls")
    ap.add_argument("--ls", type=float, default=1.0, help="length-scale a usar en --measure")
    ap.add_argument("--rolls", type=int, default=12, help="intentos máximos por escena")
    ap.add_argument("--jobs", type=int, default=min(4, os.cpu_count() or 1), help="escenas en paralelo")
    ap.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    ap.add_argument("--piper", default=shutil.which("piper") or str(Path.home() / ".local/bin/piper"))
    args = ap.parse_args()

    if not Path(args.piper).exists():
        raise SystemExit(f"no encuentro el binario de piper: {args.piper} (`uv tool install piper-tts`)")
    if not args.model.exists():
        raise SystemExit(f"no encuentro el modelo: {args.model}")

    texts = parse_texts()
    if sorted(texts) != list(range(1, 9)):
        raise SystemExit(f"guion_tts.md: esperaba esc1..esc8, encontré {sorted(texts)}")

    wanted = list(range(1, 9))
    if args.only:
        wanted = [int(x) for x in args.only.split(",")]
        bad = [n for n in wanted if n not in range(1, 9)]
        if bad:
            raise SystemExit(f"--only fuera de rango: {bad}")

    tmpdir = Path(tempfile.mkdtemp(prefix="gen-tts-"))
    synth = Synth(args.piper, args.model, tmpdir)
    budget = budgets()
    os.environ.setdefault("OMP_NUM_THREADS", "4")
    try:
        if args.measure:
            k = max(2, args.rolls)

            def calibrate(n: int):
                return [synth.roll(n - 1, texts[n], args.ls)[0] for _ in range(k)]

            with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
                samples = list(pool.map(calibrate, wanted))
            print(f"{'#':>2}  {'escena':<11} {'palabras':>8} {'media s':>8} {'sd s':>6} {'presup. s':>9} {'holgura media s':>15}")
            for n, ds in zip(wanted, samples):
                b = budget[n - 1]
                print(f"{n:>2}  {SCENE_IDS[n - 1]:<11} {len(texts[n].split()):>8} {statistics.fmean(ds):>8.3f} "
                      f"{statistics.stdev(ds):>6.3f} {b:>9.2f} {b - statistics.fmean(ds):>15.3f}")
            return 0

        with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
            results = list(pool.map(lambda n: fit(synth, n - 1, texts[n], budget[n - 1], args.rolls), wanted))

        if not args.dry_run:
            NARR.mkdir(parents=True, exist_ok=True)
            PUBLIC.mkdir(parents=True, exist_ok=True)

        print(f"{'#':>2}  {'escena':<11} {'palabras':>8} {'ls':>5} {'toma s':>8} {'presup. s':>9} "
              f"{'holgura s':>9} {'intentos':>8}  estado")
        bad = []
        for n, (ls, dur, tmp, slack, state, attempts) in zip(wanted, results):
            if not args.dry_run:
                dst, pub = NARR / f"esc{n}.wav", PUBLIC / f"esc{n}.wav"
                shutil.copyfile(tmp, dst)
                shutil.copyfile(tmp, pub)
                if sha256(dst) != sha256(pub):
                    raise SystemExit(f"esc{n}: las copias de narracion/ y public/ no coinciden")
            print(f"{n:>2}  {SCENE_IDS[n - 1]:<11} {len(texts[n].split()):>8} {ls:>5.2f} {dur:>8.3f} "
                  f"{budget[n - 1]:>9.2f} {slack:>9.3f} {len(attempts):>8}  {state}")
            if state == "WARN":
                bad.append(n)
        print(f"\n{synth.rolls} síntesis en total; "
              f"{'dry-run: no se escribió nada' if args.dry_run else f'escrito en {NARR} y {PUBLIC} (byte-idénticas)'}")
        if bad:
            print(f"AVISO: esc{','.join(map(str, bad))} quedaron fuera de la ventana 0,8–1,5 s "
                  f"(dentro del límite duro {SLACK_HARD}–{SLACK_AIR} s)", file=sys.stderr)
        return 0
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
