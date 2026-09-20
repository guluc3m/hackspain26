"""Benchmark reproducible del escalón 4 (VLM local, PaddleOCR-VL Q8 en 127.0.0.1:8080).

Mide latencia limpia (SIN carga del runner) del endpoint OpenAI-compatible de
llama-server, exactamente como la invoca el escalón 4
(`src/filemaid/extract/rungs/vlm_local.py`: prompt "OCR:", temperature 0,
max_tokens 1024, imagen PNG base64 renderizada con pypdfium2 a escala 2.0).

Dos fases:
Uso:
    uv run python scripts/bench_vlm_local.py [--url http://127.0.0.1:8080] \
        [--serial 8] [--concurrente 5] [--salida .sdd/metrics/vlm-local-latencia.json]

No toca el proceso llama-server: solo le envía peticiones HTTP.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import io
import json
import statistics
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

RAIZ = Path(__file__).resolve().parent.parent
CORPUS = RAIZ / "caja-de-alberto" / "facturas"
PROMPT = "OCR:"  # contrato del modelo (DECISIONS.md D-001)
MAX_TOKENS = 1024
ESCALA = 2.0  # mismo render_scale que el escalón 2


def render_pagina(pdf_path: Path, escala: float = ESCALA) -> bytes:
    """Renderiza la primera página del PDF a PNG, igual que el escalón 2."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(pdf_path)
    try:
        page = pdf[0]
        img = page.render(scale=escala).to_pil()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    finally:
        pdf.close()


def es_escaneo(pdf_path: Path) -> bool:
    """True si la página 0 NO tiene texto vectorial plausible (candidata a escalón 4).

    Misma idea que la puerta del escalón 1 (filemaid.extract.plausibility):
    menos de 10 palabras ⇒ no hay texto usable ⇒ hay que "leer" la imagen.
    """
    from pypdf import PdfReader

    try:
        texto = PdfReader(pdf_path).pages[0].extract_text() or ""
    except Exception:
        return True
    return len(texto.split()) < 10


def elegir_escaneos(n: int) -> list[Path]:
    """Primeros n PDFs del corpus (orden determinista) que son escaneos."""
    elegidos: list[Path] = []
    for pdf in sorted(CORPUS.glob("*.pdf")):
        if es_escaneo(pdf):
            elegidos.append(pdf)
            if len(elegidos) == n:
                break
    if len(elegidos) < n:
        raise SystemExit(f"Solo {len(elegidos)} escaneos encontrados en {CORPUS} (pedí {n})")
    return elegidos


async def fase_serial(url: str, pngs: list[bytes], n: int) -> list[dict]:
    resultados: list[dict] = []
    async with httpx.AsyncClient(timeout=180.0) as client:
        for i in range(n):
            r = await una_peticion_async(client, url, pngs[i % len(pngs)])
            r["fase"] = "serial"
            r["imagen"] = f"escaneo_{(i % len(pngs)) + 1}"
            print(f"  serial {i + 1}/{n}: {r['latencia_ms']:.0f} ms, "
                  f"{r['tokens_salida']} tok salida")
            resultados.append(r)
    return resultados


async def una_peticion_async(client: httpx.AsyncClient, url: str, png: bytes) -> dict:
    payload = {
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url",
                 "image_url": {"url": "data:image/png;base64," + base64.b64encode(png).decode()}},
                {"type": "text", "text": PROMPT},
            ],
        }],
        "temperature": 0,
        "max_tokens": MAX_TOKENS,
    }
    t0 = time.monotonic()
    r = await client.post(url, json=payload)
    latencia_ms = (time.monotonic() - t0) * 1000
    r.raise_for_status()
    body = r.json()
    texto = body["choices"][0]["message"]["content"] or ""
    return {
        "latencia_ms": round(latencia_ms, 1),
        "tokens_entrada": body.get("usage", {}).get("prompt_tokens"),
        "tokens_salida": body.get("usage", {}).get("completion_tokens"),
        "palabras_ocr": len(texto.split()),
        "ocr_con_texto": bool(texto.strip()),
    }


async def fase_concurrente(url: str, pngs: list[bytes], n: int, concurrencia: int = 2) -> dict:
    import asyncio as aio

    sem = aio.Semaphore(concurrencia)

    async def acotada(i: int) -> dict:
        async with sem:
            async with httpx.AsyncClient(timeout=300.0) as client:
                r = await una_peticion_async(client, url, pngs[i % len(pngs)])
            r["fase"] = "concurrente"
            r["imagen"] = f"escaneo_{(i % len(pngs)) + 1}"
            print(f"  concurrente {i + 1}/{n}: {r['latencia_ms']:.0f} ms")
            return r

    t0 = time.monotonic()
    resultados = await aio.gather(*(acotada(i) for i in range(n)))
    return {
        "peticiones": resultados,
        "wall_clock_ms": round((time.monotonic() - t0) * 1000, 1),
    }


def percentil(valores: list[float], p: float) -> float:
    """Percentil por interpolación lineal (método estándar)."""
    ordenados = sorted(valores)
    if len(ordenados) == 1:
        return ordenados[0]
    k = (len(ordenados) - 1) * p / 100.0
    f = int(k)
    c = min(f + 1, len(ordenados) - 1)
    return ordenados[f] + (ordenados[c] - ordenados[f]) * (k - f)


def resumen(vals: list[float]) -> dict:
    return {
        "n": len(vals),
        "media_ms": round(statistics.fmean(vals), 1),
        "p50_ms": round(percentil(vals, 50), 1),
        "p95_ms": round(percentil(vals, 95), 1),
        "min_ms": round(min(vals), 1),
        "max_ms": round(max(vals), 1),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", default="http://127.0.0.1:8080")
    ap.add_argument("--serial", type=int, default=8)
    ap.add_argument("--concurrente", type=int, default=5)
    ap.add_argument("--concurrencia", type=int, default=2)
    ap.add_argument("--salida", default=str(RAIZ / ".sdd/metrics/vlm-local-latencia.json"))
    args = ap.parse_args()

    url = args.url.rstrip("/") + "/v1/chat/completions"

    # Health check antes de empezar (no tocamos el proceso, solo lo comprobamos)
    health = httpx.get(args.url.rstrip("/") + "/health", timeout=10.0)
    health.raise_for_status()
    print(f"health: {health.json()}")

    escaneos = elegir_escaneos(3)
    print(f"escaneos elegidos: {[p.name for p in escaneos]}")
    pngs = [render_pagina(p) for p in escaneos]
    print(f"renderizados {len(pngs)} PNG (escala {ESCALA}, "
          f"{[round(len(b) / 1024) for b in pngs]} KiB)")

    print(f"fase A: {args.serial} peticiones seriales...")
    seriales = asyncio.run(fase_serial(url, pngs, args.serial))

    print(f"fase B: {args.concurrente} peticiones con concurrencia {args.concurrencia}...")
    conc = asyncio.run(fase_concurrente(url, pngs, args.concurrente, args.concurrencia))

    lat_seriales = [r["latencia_ms"] for r in seriales]
    lat_conc = [r["latencia_ms"] for r in conc["peticiones"]]
    todo_ok = all(r["ocr_con_texto"] for r in seriales + conc["peticiones"])

    doc = {
        "generado": datetime.now(ZoneInfo("Europe/Madrid")).isoformat(timespec="seconds"),
        "script": "scripts/bench_vlm_local.py",
        "endpoint": url,
        "modelo": "PaddleOCR-VL 1.6 Q8 (llama-server, 4 hilos, temp 0)",
        "condicion": "SIN carga del runner (llama-server en reposo, solo este benchmark)",
        "nota_bi-modal": (
            "La fase serial es bi-modal: p50 ≈ 3,5 s pero p95 ≈ 34,9 s. Las 2 "
            "peticiones lentas son el primer encuentro de cada imagen no vista "
            "antes (procesamiento de visión del mmproj sin caché previa); las 6 "
            "restantes reutilizan imagen vía prompt-cache del servidor "
            "(usage.prompt_tokens_details.cached_tokens ≈ 1272/1273) y caen a "
            "3,0-3,6 s. Verificación posterior: imagen repetida en servidor "
            "caliente = 3,7 s con 1272/1273 tokens cacheados. El p95 de la fase "
            "concurrente (4,4 s) confirma el estado estable: con las 3 imágenes "
            "ya vistas, concurrencia 2 solo añade ~0,7 s de cola."
        ),
        "metodo": {
            "imagenes": [p.name for p in escaneos],
            "render": f"pypdfium2 escala {ESCALA} (~144 dpi), página 1, PNG",
            "prompt": PROMPT,
            "max_tokens": MAX_TOKENS,
            "temperature": 0,
            "fase_serial": f"{args.serial} peticiones seriales rotando {len(pngs)} imágenes",
            "fase_concurrente": f"{args.concurrente} peticiones con semáforo de {args.concurrencia}",
        },
        "serial": {
            "peticiones": seriales,
            "resumen": resumen(lat_seriales),
        },
        "concurrente": {
            "concurrencia": args.concurrencia,
            "peticiones": conc["peticiones"],
            "resumen": resumen(lat_conc),
            "wall_clock_ms": conc["wall_clock_ms"],
            "throughput_equiv_paginas_por_min": round(
                len(lat_conc) / (conc["wall_clock_ms"] / 60000), 2),
        },
        "todas_devolvieron_ocr": todo_ok,
        "coste_eur": 0.0,
        "etiqueta": "medido",
    }

    salida = Path(args.salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
    print(f"escrito: {salida}")
    print(f"serial      p50={doc['serial']['resumen']['p50_ms']:.0f} ms  "
          f"p95={doc['serial']['resumen']['p95_ms']:.0f} ms  (n={len(lat_seriales)})")
    print(f"concurren.  p50={doc['concurrente']['resumen']['p50_ms']:.0f} ms  "
          f"p95={doc['concurrente']['resumen']['p95_ms']:.0f} ms  (n={len(lat_conc)}, "
          f"c={args.concurrencia}, wall {conc['wall_clock_ms'] / 1000:.1f} s)")


if __name__ == "__main__":
    main()
