#!/usr/bin/env python3
"""Genera video/public/music.wav: pad ambiental suave de 180,0 s exactos.

Solo stdlib (wave, math, struct, random). Reproducible: semilla fija.

Características:
- Mono 44100 Hz, 16-bit PCM.
- Progresión de acordes lenta tipo F - Am - Dm - C en registro medio-grave,
  ~12 s por acorde con crossfade de 3 s entre acordes (sin clics: la
  envolvente de cada acorde vale 0 en sus bordes y las fases son continuas
  por acumulador de fase dentro de cada voz).
- Ondas senoidales con envolventes suaves (attack/release 3 s) y una
  envolvente de "respiración" lenta por voz.
- Sin percusión ni ritmo marcado. Volumen bajo (pico objetivo < 0.5).
- Fade-in global de 3 s y fade-out global de 5 s.
"""

import math
import random
import struct
import wave

# --- Configuración -------------------------------------------------------
SR = 44100          # Hz
DUR = 180.0         # s exactos
SEED = 20260920     # semilla fija: salida reproducible

OUT = "public/music.wav"

CHORD_LEN = 12.0    # s de duración nominal de cada acorde
XFADE = 3.0         # s de crossfade entre acordes (attack = release = XFADE)
FADE_IN = 3.0       # s de fade-in global
FADE_OUT = 5.0      # s de fade-out global
TARGET_PEAK = 0.38  # pico objetivo tras normalizar (muy por debajo de 0.5)

# Progresión calma en registro medio-grave (números MIDI).
# [sub grave (opcional), raíz media, quinta, décima/tercera superior]
PROGRESSION = [
    [41, 53, 60, 69],   # F:  F2 - F3 - C4 - A4
    [45, 57, 64, 72],   # Am: A2 - A3 - E4 - C5
    [38, 50, 62, 69],   # Dm: D2 - D3 - D4 - A4
    [36, 48, 55, 64],   # C:  C2 - C3 - G3 - E4
]
# Ganancia relativa por voz: sub grave suave, cuerpo medio, brillo leve.
VOICE_GAIN = [0.55, 1.0, 0.85, 0.6]


def midi_to_hz(m: int) -> float:
    """Convierte una nota MIDI a hercios."""
    return 440.0 * (2.0 ** ((m - 69) / 12.0))


def build_sample(rng: random.Random) -> list[float]:
    """Sintetiza la pista completa y devuelve las muestras float en [-1, 1]."""
    n_total = round(DUR * SR)  # 7_938_000 muestras exactas
    buf = [0.0] * n_total

    period = CHORD_LEN - XFADE  # 9.0 s entre inicios de acorde
    n_chords = math.ceil(DUR / period) + 1

    for ci in range(n_chords):
        t0 = ci * period
        seg_start = max(0, round((t0 - XFADE) * SR))
        seg_end = min(n_total, round((t0 + CHORD_LEN + XFADE) * SR))
        if seg_start >= seg_end:
            continue
        chord = PROGRESSION[ci % len(PROGRESSION)]

        for vi, midi in enumerate(chord):
            f = midi_to_hz(midi)
            # Detune diminuto y estable por voz/acorde (calor, menos pureza).
            f *= 1.0 + rng.uniform(-0.0015, 0.0015)
            g = VOICE_GAIN[vi % len(VOICE_GAIN)] * 0.10
            # "Respiración" lenta de amplitud, fase aleatoria estable.
            lfo_hz = rng.uniform(0.05, 0.11)
            lfo_ph = rng.uniform(0.0, 2.0 * math.pi)
            lfo_amt = 0.25

            phase = rng.uniform(0.0, 2.0 * math.pi)
            w = 2.0 * math.pi * f / SR
            lfo_w = 2.0 * math.pi * lfo_hz / SR

            fade_n = XFADE * SR  # attack y release dentro del crossfade
            span = seg_end - seg_start
            for k in range(span):
                # Envolvente del acorde: attack/release coseno elevado.
                # Vale exactamente 0 en ambos extremos del segmento.
                if k < fade_n:
                    env = 0.5 - 0.5 * math.cos(math.pi * k / fade_n)
                elif k > span - fade_n:
                    env = 0.5 - 0.5 * math.cos(math.pi * (span - k) / fade_n)
                else:
                    env = 1.0

                breathe = 1.0 - lfo_amt + lfo_amt * math.sin(lfo_w * k + lfo_ph)
                buf[seg_start + k] += env * breathe * g * math.sin(phase)
                phase += w

    # Fade-in / fade-out globales.
    fi = int(FADE_IN * SR)
    fo = int(FADE_OUT * SR)
    for i in range(fi):
        buf[i] *= 0.5 - 0.5 * math.cos(math.pi * i / fi)
    for i in range(fo):
        buf[n_total - 1 - i] *= 0.5 - 0.5 * math.cos(math.pi * i / fo)

    # Normaliza al pico objetivo (garantiza pico < 0.5 sin clipear).
    peak = max(abs(v) for v in buf) if buf else 0.0
    if peak > 0.0:
        scale = min(1.0, TARGET_PEAK / peak)
        if scale < 1.0:
            buf = [v * scale for v in buf]
    return buf


def main() -> None:
    rng = random.Random(SEED)
    samples = build_sample(rng)
    n = len(samples)

    # Clamp de seguridad + cuantización a 16-bit.
    frames = struct.pack(
        f"<{n}h",
        *(max(-32768, min(32767, round(s * 32767.0))) for s in samples)
    )

    with wave.open(OUT, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(frames)

    peak = max(abs(s) for s in samples)
    print(f"escrito {OUT}: {n} muestras, {n / SR:.6f} s, pico {peak:.4f}")


if __name__ == "__main__":
    main()
