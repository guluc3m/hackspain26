"""Telemetría continua del sistema (T31) — todo medido, nada inventado.

Tres piezas, todas aditivas (el motor y las reglas no se tocan):

1. `stats_por_rung` — serie comparable POR RUNG desde las filas de evidencia
   del ledger: nº ejecuciones, p50/p95, ratio de descarte y coste acumulado,
   en ventanas (corrida actual / última hora / histórico). Fuente citada:
   stage+latencia+outcome de las filas que ya existen.

2. `stats_vlm` — rung 4 (llama-server) y rung 5 (cloud) como ciudadanos de
   primera: invocaciones, latencia media/máx, cache hit/miss por
   (page_sha256, engine, config_version) leyendo el cache real, tasa de
   truncado (si la evidencia la registra), y en rung 5 facturables vs
   cacheadas con su coste (fórmula T9 intacta).

3. `sonda_llama` — sondea /metrics (Prometheus) y /props del sidecar:
   uptime de componentes y cola rung 4 para Operaciones. Down ⇒ «sin datos»,
   jamás ceros falsos.

4. `EventChain` — log de eventos encadenado con hash (trazabilidad total):
   cada evento sella el hash del anterior; la verificación recalcula la
   cadena y delata cualquier manipulación.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from pathlib import Path
from typing import Any

from albertitos.metrics import PRECIOS

RUNG_RE = re.compile(r"rung(\d+)")


def _rung_de(stage: str, extractor: str) -> str:
    m = RUNG_RE.search(stage)
    if m:
        return f"rung{m.group(1)}"
    return extractor or "desconocido"


def _p50(valores: list[float]) -> float:
    if not valores:
        return 0.0
    return sorted(valores)[len(valores) // 2]


def _p95(valores: list[float]) -> float:
    if not valores:
        return 0.0
    ordenados = sorted(valores)
    return ordenados[max(0, math.ceil(0.95 * len(ordenados)) - 1)]


# ------------------------------------------------------------- stats por rung


def stats_por_rung(
    registros: list[dict[str, Any]], ahora: float | None = None
) -> dict[str, Any]:
    """Serie comparable por rung en ventanas, desde filas de evidencia crudas.

    Los registros son dicts JSONL del ledger (kind/event = evidence) con
    stage, latency_ms, outcome y cost_eur opcional. El campo `timestamp` es
    OPCIONAL: si las filas no lo llevan, la ventana «última hora» queda
    «sin datos» en vez de falsear la serie.
    """
    ahora = ahora if ahora is not None else time.time()
    evidencia = [r for r in registros if (r.get("kind") or r.get("event")) == "evidence"]
    ventanas: dict[str, str] = {"corrida": "histórico completo del ledger", "ultima_hora": "", "historico": ""}

    def _stat(de: list[dict[str, Any]]) -> dict[str, Any]:
        por_rung: dict[str, dict[str, Any]] = {}
        total_filas = 0
        for e in de:
            rung = _rung_de(str(e.get("stage", "")), str(e.get("extractor", "")))
            outcome = str(e.get("outcome", ""))
            es_skip = outcome.startswith("skipped")
            grupo = por_rung.setdefault(
                rung, {"n": 0, "latencias": [], "omitidos": 0, "errores": 0, "coste_eur": 0.0}
            )
            grupo["n"] += 1
            if es_skip:
                grupo["omitidos"] += 1
            elif outcome == "error":
                grupo["errores"] += 1
            elif isinstance(e.get("latency_ms"), int) and e["latency_ms"] > 0:
                grupo["latencias"].append(float(e["latency_ms"]))
            coste = e.get("cost_eur")
            if isinstance(coste, (int, float)):
                grupo["coste_eur"] += float(coste)
            elif rung in ("rung5", "cloud_vlm") and not es_skip:
                # nº llamadas × precio (config T9 — fórmula intacta)
                grupo["coste_eur"] += float(PRECIOS["cloud"]["eur_por_llamada"])
            total_filas += 1
        salida: dict[str, Any] = {}
        for rung in sorted(por_rung):
            g = por_rung[rung]
            lat = g["latencias"]
            salida[rung] = {
                "n": g["n"],
                "p50_ms": round(_p50(lat), 1) if lat else None,
                "p95_ms": round(_p95(lat), 1) if lat else None,
                "ratio_descarte": (
                    round(100 * g["omitidos"] / g["n"], 1) if g["n"] else None
                ),
                "errores": g["errores"],
                "coste_eur": round(g["coste_eur"], 4),
                "pct_filas": (
                    round(100 * g["n"] / total_filas, 1) if total_filas else None
                ),
            }
        return {"rungs": salida, "total_filas": total_filas}

    # «corrida actual»: el ledger es append-only, así que la config_version de
    # la ÚLTIMA fila es la corrida más reciente (medido, sin adivinar).
    corrida_actual_cv = ""
    for e in evidencia:
        corrida_actual_cv = str(e.get("config_version", "?"))
    corrida_actual = _stat([e for e in evidencia if str(e.get("config_version", "?")) == corrida_actual_cv])
    con_ts = [e for e in evidencia if isinstance(e.get("timestamp"), (int, float))]
    if con_ts:
        hora = _stat([e for e in con_ts if float(e["timestamp"]) >= ahora - 3600])
    else:
        hora = {"rungs": {}, "total_filas": 0, "sin_timestamps": len(evidencia)}
    return {
        "ventanas": {
            "corrida_actual": corrida_actual,
            "ultima_hora": hora,
            "historico": _stat(evidencia),
        },
        "ventanas_nota": ventanas,
    }


# ------------------------------------------------------------------ stats VLM


def stats_vlm(
    registros: list[dict[str, Any]],
    cache_root: Path | None = None,
) -> dict[str, Any]:
    """Stats del VLM (rung 4 llama-server y rung 5 cloud) como ciudadano de
    primera: invocaciones, latencias, cache hit/miss por página real, tasa de
    truncado y coste facturable de rung 5 (nº llamadas × precio, T9)."""
    evidencia = [r for r in registros if (r.get("kind") or r.get("event")) == "evidence"]
    out: dict[str, Any] = {}
    for nombre, rungs in (("rung4_llama_server", ("rung4", "vlm")), ("rung5_cloud", ("rung5", "cloud_vlm"))):
        filas = [
            e
            for e in evidencia
            if _rung_de(str(e.get("stage", "")), str(e.get("extractor", ""))) in rungs
        ]
        latencias = [
            float(e["latency_ms"])
            for e in filas
            if isinstance(e.get("latency_ms"), int) and e["latency_ms"] > 0
            and str(e.get("outcome", "")) not in ("skipped", "error")
        ]
        omitidas = sum(1 for e in filas if str(e.get("outcome", "")).startswith("skipped"))
        errores = sum(1 for e in filas if str(e.get("outcome", "")) == "error")
        truncadas = sum(1 for e in filas if "truncat" in str(e.get("outcome", "")).lower()
                        or "truncat" in str(e.get("detail", "")).lower())
        tokens = [
            e for e in filas
            if "tokens" in str(e.get("detail", "")).lower()
        ]
        emitidas = len(filas) - omitidas  # llamadas emitidas (facturables o cacheadas)
        # hit LITERAL ("cache hit"); un "cache miss" es un miss, no un hit
        cacheadas = sum(
            1 for e in filas
            if "cache hit" in str(e.get("outcome", "")).lower()
            or "cache hit" in str(e.get("detail", "")).lower()
        )
        precio = float(PRECIOS["cloud"]["eur_por_llamada"])
        facturables = max(0, emitidas - cacheadas)
        out[nombre] = {
            "n_invocaciones": emitidas,
            "latencia_media_ms": round(sum(latencias) / len(latencias), 1) if latencias else None,
            "latencia_max_ms": round(max(latencias), 1) if latencias else None,
            "omitidas": omitidas,
            "errores": errores,
            "cache_hit": cacheadas,
            "cache_miss": max(0, emitidas - cacheadas),
            "tasa_truncado": (
                round(100 * truncadas / emitidas, 1) if emitidas else None
            ),
            "tokens_registrados": len(tokens) if tokens else 0,
            "coste_eur": (
                {"valor": f"{facturables * precio:.4f} EUR"}
                if rungs[0] == "rung5"
                else {"valor": "0.0000 EUR (local)"}
            ),
        }
    # cache real por (page_sha256, engine, config_version): ficheros en el dir
    if cache_root is not None and Path(cache_root).is_dir():
        n_cache = sum(1 for _ in Path(cache_root).rglob("*.json"))
        out["cache_paginas_almacenadas"] = {"valor": str(n_cache)}
    return out


# --------------------------------------------------------------- sonda llama


def sonda_llama(base_url: str = "http://127.0.0.1:8080", timeout_s: float = 2.0) -> dict[str, Any]:
    """Sondea /health, /props y /metrics del sidecar. Down ⇒ «sin datos»."""
    import httpx

    out: dict[str, Any] = {"url": base_url, "estado": "down"}
    try:
        r = httpx.get(f"{base_url}/health", timeout=timeout_s)
        if r.status_code != 200:
            return out
    except httpx.HTTPError:
        return out
    out["estado"] = "up"
    props = _cargar_json_url(f"{base_url}/props", timeout_s)
    if props:
        out["modelo"] = str(props.get("model", "—"))
    metrics = _texto_url(f"{base_url}/metrics", timeout_s)
    if metrics:
        contadores = {}
        for clave in ("llamacpp:prompt_tokens_total", "llamacpp:tokens_total",
                      "llamacpp:prompt_eval_total_seconds", "llamacpp:eval_total_seconds"):
            m = re.search(rf"^{re.escape(clave)}\s+(\S+)", metrics, re.MULTILINE)
            if m:
                contadores[clave.split(":")[1]] = float(m.group(1))
        if contadores:
            out["contadores"] = contadores
        cola = re.search(r"llamacpp:requests_processing\s+(\S+)", metrics)
        if cola:
            out["cola_rung4"] = cola.group(1)
    return out


def _texto_url(url: str, timeout_s: float) -> str | None:
    import httpx

    try:
        r = httpx.get(url, timeout=timeout_s)
        return r.text if r.status_code == 200 else None
    except httpx.HTTPError:
        return None


def _cargar_json_url(url: str, timeout_s: float) -> dict | None:
    import httpx

    try:
        r = httpx.get(url, timeout=timeout_s)
        return r.json() if r.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        return None


# ----------------------------------------------------------------- EventChain


class EventChain:
    """Log de eventos encadenado con hash — trazabilidad total y manipulable
    de auditar: cada evento sella el hash del anterior
    (hash = sha256(prev_hash + payload)); `verificar()` recalcula la cadena."""

    def __init__(self, ruta: Path | str):
        self.ruta = Path(ruta)

    def _ultimo(self) -> tuple[int, str]:
        seq, prev_hash = 0, "0" * 64
        if self.ruta.is_file():
            for linea in self.ruta.read_text(encoding="utf-8").splitlines():
                if not linea.strip():
                    continue
                try:
                    rec = json.loads(linea)
                except json.JSONDecodeError:
                    continue
                seq, prev_hash = int(rec.get("seq", 0)), str(rec.get("hash", prev_hash))
        return seq, prev_hash

    def append(self, evento: str, detalle: dict[str, Any] | None = None) -> dict[str, Any]:
        seq, prev_hash = self._ultimo()
        rec = {
            "seq": seq + 1,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "evento": evento,
            "detalle": detalle or {},
            "prev_hash": prev_hash,
        }
        payload = json.dumps(rec, sort_keys=True, ensure_ascii=False)
        rec["hash"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        with self.ruta.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec

    def leer(self) -> list[dict[str, Any]]:
        eventos: list[dict[str, Any]] = []
        if self.ruta.is_file():
            for linea in self.ruta.read_text(encoding="utf-8").splitlines():
                if linea.strip():
                    try:
                        eventos.append(json.loads(linea))
                    except json.JSONDecodeError:
                        continue
        return eventos

    def verificar(self) -> dict[str, Any]:
        """Recalcula la cadena: {ok, n, primer_hash_roto} — ROJO si alguien
        manipula un evento intermedio."""
        prev = "0" * 64
        seq_esperada = 1
        for rec in self.leer():
            copia = {k: v for k, v in rec.items() if k != "hash"}
            esperado = hashlib.sha256(
                json.dumps(copia, sort_keys=True, ensure_ascii=False).encode("utf-8")
            ).hexdigest()
            if rec.get("prev_hash") != prev or rec.get("hash") != esperado or rec.get("seq") != seq_esperada:
                return {"integra": False, "n": seq_esperada - 1, "roto_en_seq": rec.get("seq")}
            prev, seq_esperada = rec["hash"], rec["seq"] + 1
        return {"integra": True, "n": seq_esperada - 1, "roto_en_seq": None}

def main(argv: list[str] | None = None) -> int:
    """CLI: stats por rung + VLM + sonda llama + verificación de la cadena."""
    import argparse

    from albertitos.ui.ledger import load_ledger

    parser = argparse.ArgumentParser(
        prog="albertitos.telemetria", description="Telemetría continua (T31)."
    )
    parser.add_argument("--store", default=".sdd/lote1/ledger")
    parser.add_argument("--cache", default=".sdd/lote1/cache")
    parser.add_argument("--actividad", default=".sdd/telemetria/actividad.jsonl")
    parser.add_argument("--llama-url", default="http://127.0.0.1:8080")
    args = parser.parse_args(argv)
    registros = load_ledger(Path(args.store))
    stats = stats_por_rung(registros)
    print("== Escalera (corrida actual) ==")
    for rung, s in stats["ventanas"]["corrida_actual"]["rungs"].items():
        print(f"  {rung}: n={s['n']} · p50 {s['p50_ms']} ms · p95 {s['p95_ms']} ms · "
              f"{s['pct_paginas']} % páginas · coste {s['coste_eur']} EUR")
    vlm = stats_vlm(registros, cache_root=Path(args.cache) if Path(args.cache).is_dir() else None)
    for nombre, s in vlm.items():
        if isinstance(s, dict) and "n_invocaciones" in s:
            print(f"VLM {nombre}: {s['n_invocaciones']} invocaciones · "
                  f"lat media {s['latencia_media_ms']} ms · cache {s['cache_hit']}/{s['cache_miss']} · {s['coste_eur']['valor']}")
    print(f"Sonda llama: {sonda_llama(args.llama_url)['estado'][0]}")
    cadena = EventChain(args.actividad)
    verif = cadena.verificar()
    print(f"Cadena de actividad: {'íntegra' if verif['integra'] else 'ROTO'} "
          f"({verif['n']} eventos)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
