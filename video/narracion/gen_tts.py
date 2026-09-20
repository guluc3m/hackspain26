#!/usr/bin/env python3
"""Genera la voz narrada del vídeo (esc1..esc8) con piper.

Los textos salen de `guion_tts.md` (fuente de verdad narrativa: este script no
los reescribe). El ritmo se autoregula por escena con `--length-scale` para que
cada toma **llene** su escena: holgura objetivo 0,8–1,5 s, nunca menos de 0,5 s
(límite duro) ni más de 2,0 s (aire muerto).

    presupuesto = frames/30 − VOZ_delay ;  holgura = presupuesto − toma

Escribe `video/narracion/escN.wav` y su copia byte-idéntica en
`video/public/narracion/escN.wav` (la que sirve `staticFile`).

Uso:
    python3 narracion/gen_tts.py                 # regenera las 8 tomas
    python3 narracion/gen_tts.py --only 3,5,7    # solo algunas escenas
    python3 narracion/gen_tts.py --dry-run       # mide y reporta, no escribe
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
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

SLACK_MIN = 0.8
SLACK_MAX = 1.5
SLACK_HARD = 0.5
SLACK_TARGET = (SLACK_MIN + SLACK_MAX) / 2
LS_MIN, LS_MAX, LS_TOL = 0.90, 1.12, 0.005

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
    """piper envuelto: sintetiza a wav temporal y mide la duración."""

    def __init__(self, piper: str, model: Path, tmpdir: Path):
        self.piper = piper
        self.model = model
        self.tmpdir = tmpdir
        self.cache: dict[tuple[int, float], tuple[float, Path]] = {}

    def at(self, idx: int, text: str, ls: float) -> tuple[float, Path]:
        key = (idx, round(ls, 4))
        if key in self.cache:
            return self.cache[key]
        out = self.tmpdir / f"esc{idx + 1}-ls{ls:.4f}.wav"
        cmd = [self.piper, "-m", str(self.model), "-f", str(out), "--length-scale", f"{ls:.4f}"]
        res = subprocess.run(cmd, input=text.encode("utf-8"), capture_output=True)
        if res.returncode != 0:
            raise SystemExit(f"piper falló (esc{idx + 1}, ls={ls}):\n{res.stderr.decode('utf-8', 'replace')}")
        measured = (wav_seconds(out), out)
        self.cache[key] = measured
        return measured


def fit(synth: Synth, idx: int, text: str, budget: float) -> tuple[float, float, Path, str]:
    """Busca el `--length-scale` que deja la holgura más cerca del objetivo."""
    d_slow, p_slow = synth.at(idx, text, LS_MAX)
    slack_slow = budget - d_slow
    if slack_slow > SLACK_MAX:
        return LS_MAX, d_slow, p_slow, "AIRE"

    d_fast, p_fast = synth.at(idx, text, LS_MIN)
    slack_fast = budget - d_fast
    if slack_fast < SLACK_HARD:
        return LS_MIN, d_fast, p_fast, "FUERA"

    lo, hi = LS_MIN, LS_MAX
    while hi - lo > LS_TOL:
        mid = (lo + hi) / 2
        d_mid, _ = synth.at(idx, text, mid)
        if budget - d_mid > SLACK_TARGET:
            lo = mid
        else:
            hi = mid

    best = None
    for ls in (lo, hi, (lo + hi) / 2):
        d, p = synth.at(idx, text, ls)
        err = abs((budget - d) - SLACK_TARGET)
        if best is None or err < best[3]:
            best = (ls, d, p, err)
    ls, d, p, _ = best
    slack = budget - d
    state = "OK" if SLACK_MIN <= slack <= SLACK_MAX else ("HOLGURA BAJA" if slack >= SLACK_HARD else "FUERA")
    return ls, d, p, state


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="índices 1..8 separados por comas (por defecto: todas)")
    ap.add_argument("--dry-run", action="store_true", help="mide y reporta sin escribir wavs")
    ap.add_argument("--jobs", type=int, default=min(4, os.cpu_count() or 1), help="escenas en paralelo")
    ap.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    ap.add_argument("--piper", default=shutil.which("piper") or str(Path.home() / ".local/bin/piper"))
    args = ap.parse_args()

    if not Path(args.piper).exists():
        raise SystemExit(f"no encuentro el binario de piper: {args.piper} (instala con `uv tool install piper-tts`)")
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

    synth = Synth(args.piper, args.model, Path(tempfile.mkdtemp(prefix="gen-tts-")))
    budgets = [FRAMES[i] / FPS - VOZ_FRAMES[i] / FPS for i in range(8)]

    try:
        os.environ.setdefault("OMP_NUM_THREADS", "4")
        with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
            results = list(pool.map(lambda n: fit(synth, n - 1, texts[n], budgets[n - 1]), wanted))

        if not args.dry_run:
            NARR.mkdir(parents=True, exist_ok=True)
            PUBLIC.mkdir(parents=True, exist_ok=True)

        rows = []
        for n, (ls, dur, tmp, state) in zip(wanted, results):
            idx = n - 1
            budget = budgets[idx]
            slack = budget - dur
            if not args.dry_run:
                dst = NARR / f"esc{n}.wav"
                pub = PUBLIC / f"esc{n}.wav"
                shutil.copyfile(tmp, dst)
                shutil.copyfile(tmp, pub)
                if sha256(dst) != sha256(pub):
                    raise SystemExit(f"esc{n}: las copias de narracion/ y public/ no coinciden")
            rows.append((n, ls, dur, budget, slack, state))

        print(f"{'#':>2}  {'escena':<11} {'palabras':>8} {'ls':>6} {'toma s':>8} {'presup. s':>9} {'holgura s':>9}  estado")
        for n, ls, dur, budget, slack, state in rows:
            print(f"{n:>2}  {SCENE_IDS[n - 1]:<11} {len(texts[n].split()):>8} {ls:>6.3f} {dur:>8.3f} {budget:>9.2f} {slack:>9.3f}  {state}")
        if not args.dry_run:
            print(f"\nescrito {len(rows)} toma(s) en {NARR} y {PUBLIC} (byte-idénticas)")
        else:
            print("\n(dry-run: no se escribió nada)")

        bad = [r for r in rows if r[5] == "FUERA"]
        if bad:
            for n, _, dur, budget, slack, _ in bad:
                need = "más corto" if slack < 0 else "más largo"
                print(f"ERROR esc{n}: toma {dur:.3f} s, presupuesto {budget:.2f} s, holgura {slack:.3f} s "
                      f"(límite duro {SLACK_HARD} s) — el texto debe ser {need}", file=sys.stderr)
            return 1
        return 0
    finally:
        shutil.rmtree(synth.tmpdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
