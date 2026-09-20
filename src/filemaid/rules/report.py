"""Informe visual de decisiones: HTML por factura + índice, local a rules/.

Lee PouchDB (decisions, rule_evaluations, fields, features) y recompute
los breadcrumbs del colapso con `escoger` (puro y determinista: mismos
candidatos + misma config ⇒ mismo audit). El HTML es estático y autocontenido:
se abre con file:// sin servidor.
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment

from filemaid.config import AppConfig
from filemaid.rules.config import RuleConfig
from filemaid.rules.escoger import escoger, field_selection
from filemaid.store.pouch import PouchStore
from filemaid.store.queries import archive_output
from filemaid.types import ExtractionField

_ESTATUS_CLASE = {
    "ELEGIDO": "ok",
    "RECHAZADO_UMBRAL": "bad",
    "MENOR_PUNTUACION": "muted",
    "DESVANTAJA_DESEMPATE": "warn",
}
_VEREDICTO_CLASE = {"PASS": "ok", "FAIL": "bad", "UNKNOWN": "warn"}
_RESULTADO_CLASE = {"PAGAR": "ok", "NO_PAGAR": "bad", "ESCALAR": "warn"}

# Etiquetas legibles de los códigos estables de causa UNKNOWN (types.UNKNOWN_*)
_CATEGORIA_LABEL = {
    "SIN_CAMPO": "sin campo",
    "SIN_CANDIDATO_VALIDO": "ningún candidato supera formato y umbral",
    "CONFIANZA_BAJA": "confianza por debajo del umbral",
    "NO_PARSEABLE": "valor no parseable",
    "CRUZ_NO_POSIBLE": "cruce imposible (maestro/ERP)",
    "OTRO": "otro",
}


def _categoria(code: str) -> str:
    return _CATEGORIA_LABEL.get(code, code or "otro")


def _estatus_clase(status: str) -> str:
    if status in _ESTATUS_CLASE:
        return _ESTATUS_CLASE[status]
    return "bad" if status.startswith("RECHAZADO_FORMATO") else "muted"


def _dt(ts: float | None) -> str:
    if not ts:
        return "—"
    return datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")


def _display(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _field_breadcrumbs(
    candidates: list[dict[str, Any]], field_type: str, seleccion: dict[str, Any]
) -> dict[str, Any]:
    """Recompute determinista del colapso: qué pasó con cada candidato."""
    f = ExtractionField(type=field_type)
    for c in candidates:
        f.add(c["extractor"], c["value"], float(c["confidence"]))
    sel_cfg = field_selection(seleccion, field_type)
    sel = escoger(f, sel_cfg)
    rows = []
    for a in sel.audit:
        weight = sel_cfg.extractor_weights.get(a.extractor, 1.0)
        rows.append(
            {
                "extractor": a.extractor,
                "value": _display(a.value),
                "confidence": a.confidence,
                "weight": weight,
                "score": a.score,
                "status": a.status,
                "status_class": _estatus_clase(a.status),
                "reason": a.reason,
            }
        )
    chosen = None
    if sel.candidate is not None:
        chosen = {
            "extractor": sel.candidate.extractor,
            "value": _display(sel.candidate.value),
            "confidence": sel.candidate.confidence,
            "why": sel.why,
        }
    return {
        "type": field_type,
        "candidates": rows,
        "chosen": chosen,
        "collapse_reason": sel.reason,
        "collapse_code": sel.reason_code,
        "collapse_label": _categoria(sel.reason_code) if sel.reason_code else "",
        "format_tests": list(sel_cfg.format_tests),
        "score_threshold": sel_cfg.score_threshold,
    }


def collect_invoice(
    store: PouchStore,
    item: dict | str,
    seleccion: dict[str, Any],
) -> dict[str, Any]:
    """Una factura: decisión, reglas, breadcrumbs de campos y escalera."""
    if isinstance(item, str):
        doc = store.get(f"decision:{item}")
        if doc is None:
            raise KeyError(f"No decision found for scan {item}")
        d = store.hydrate(doc)
    else:
        d = store.hydrate(item)

    scan_id = d.get("scan_id", "")
    file_id = d.get("file_id", "")
    file_key = d.get("file_key", "")
    invoice_id = d.get("invoice_id", "")
    run_id = d.get("run_id", "")
    timestamp = d.get("timestamp", 0.0)

    sha256 = d.get("sha256", "")
    if not sha256 and file_key:
        scan_doc = store.get(f"scan:{file_key}:{scan_id}")
        if scan_doc:
            sha256 = scan_doc.get("sha256", "")
        if not sha256:
            file_doc = store.get(f"file:{file_key}")
            if file_doc:
                sha256 = file_doc.get("sha256", "")

    dec = d.get("decision", {})
    result = dec.get("result", "")
    if hasattr(result, "value"):
        result = result.value
    result = str(result)

    snapshot = dec.get("config_snapshot", {})
    if is_dataclass(snapshot):
        snapshot = asdict(snapshot)

    extraction_ms = int(dec.get("extraction_ms", 0) or 0)
    parser_ms = int(dec.get("parser_ms", 0) or 0)
    evaluation_ms = int(dec.get("evaluation_ms", 0) or 0)
    total_ms = int(dec.get("total_ms", 0) or 0)
    timings = dec.get("timings", {})
    if isinstance(timings, str):
        try:
            timings = json.loads(timings)
        except Exception:
            timings = {}

    evals = []
    rule_evals = dec.get("rule_evaluations", [])
    for r in rule_evals:
        if is_dataclass(r):
            r = asdict(r)
        verdict = r.get("verdict", "")
        if hasattr(verdict, "value"):
            verdict = verdict.value
        verdict = str(verdict)
        consumed = r.get("consumed", {})
        if isinstance(consumed, str):
            try:
                consumed = json.loads(consumed)
            except Exception:
                consumed = {}
        evals.append(
            {
                "code": r.get("code", ""),
                "verdict": verdict,
                "verdict_class": _VEREDICTO_CLASE.get(verdict, "muted"),
                "reason": r.get("reason", ""),
                "reason_code": r.get("reason_code", ""),
                "reason_label": _categoria(r.get("reason_code", ""))
                if verdict == "UNKNOWN"
                else "",
                "consumed": consumed,
                "consumed_pairs": [(k, _display(v)) for k, v in sorted(consumed.items())],
            }
        )

    fails = [e for e in evals if e["verdict"] == "FAIL"]
    unknowns = [e for e in evals if e["verdict"] == "UNKNOWN"]
    on_fail = {str(k): str(v) for k, v in (snapshot.get("rule_outcomes") or {}).items()}
    definitivos = [e for e in fails if on_fail.get(e["code"], "NO_PAGAR") != "ESCALAR"]
    escalados = [e for e in fails if on_fail.get(e["code"], "NO_PAGAR") == "ESCALAR"]
    if result == "NO_PAGAR":
        drivers, driver_kind = definitivos, "negativos definitivos (FAIL): no se paga"
    elif result == "ESCALAR":
        drivers = escalados + unknowns
        if escalados:
            driver_kind = (
                "regla rota configurada como escalable (FAIL→ESCALAR) "
                "o duda razonable (UNKNOWN): se escala"
            )
        else:
            driver_kind = "duda razonable (UNKNOWN): se escala"
    else:
        drivers, driver_kind = [], "todas las reglas PASS: se paga"
    driver_ids = {id(e) for e in drivers}
    for e in evals:
        e["is_driver"] = id(e) in driver_ids

    fields_doc = store.get(f"fields:{scan_id}")
    fields_dict: dict[str, list[dict[str, Any]]] = {}
    if fields_doc:
        fields_doc = store.hydrate(fields_doc)
        for f in fields_doc.get("fields", []):
            f_type = f.get("type", "")
            cands = f.get("values", [])
            fields_dict[f_type] = [
                {
                    "extractor": c.get("extractor", ""),
                    "value": c.get("value"),
                    "confidence": c.get("confidence", 0.0),
                }
                for c in cands
            ]
    fields = _field_breadcrumbs_all(fields_dict, seleccion)

    feature_docs = store.list(f"feature:{scan_id}:")
    features = [store.hydrate(feat) for feat in feature_docs]
    pages = _ladder(features)

    return {
        "invoice_id": invoice_id,
        "file_id": file_id,
        "sha256": sha256,
        "run_id": run_id,
        "scan_id": scan_id,
        "result": result,
        "result_class": _RESULTADO_CLASE.get(result, "muted"),
        "timestamp": timestamp,
        "timestamp_iso": _dt(timestamp),
        "snapshot": snapshot,
        "evaluations": evals,
        "drivers": drivers,
        "driver_kind": driver_kind,
        "counts": {
            "PASS": sum(1 for e in evals if e["verdict"] == "PASS"),
            "FAIL": len(fails),
            "UNKNOWN": len(unknowns),
        },
        "extraction_ms": extraction_ms,
        "parser_ms": parser_ms,
        "evaluation_ms": evaluation_ms,
        "total_ms": total_ms,
        "timings": timings,
        "fields": fields,
        "pages": pages,
    }


def _field_breadcrumbs_all(
    fields: dict[str, list[dict[str, Any]]], seleccion: dict[str, Any]
) -> list[dict[str, Any]]:
    return [_field_breadcrumbs(cands, t, seleccion) for t, cands in sorted(fields.items())]


def _ladder(features: list) -> list[dict[str, Any]]:
    pages: dict[Any, list[dict[str, Any]]] = {}
    for feat in features:
        f_data = feat.get("feature", {})
        stage = feat.get("stage") or f_data.get("extraction_method", "").split(":")[0]
        outcome = f_data.get("extraction_method", stage)
        confidence = f_data.get("confidence")
        latency_ms = f_data.get("latency_ms", 0)
        extractor_version = f_data.get("extractor_version", "")
        page = feat.get("page")
        if page is None:
            page = f_data.get("page")
        pages.setdefault(page, []).append(
            {
                "stage": stage,
                "outcome": outcome,
                "confidence": confidence,
                "latency_ms": latency_ms,
                "extractor_version": extractor_version,
                "skipped": str(outcome).startswith("skipped:"),
            }
        )
    ordered = sorted(pages, key=lambda p: (p is None, p if p is not None else -1))
    return [{"page": p if p is not None else None, "rungs": pages[p]} for p in ordered]


def collect_run(store: PouchStore, cfg: AppConfig, run_id: str) -> dict[str, Any]:
    """Un run: resumen + una entrada por factura (index.html)."""
    rc = RuleConfig.load(cfg.rules_config_path)
    matching_decisions = []
    for raw in store.list("decision:"):
        d = store.hydrate(raw)
        if d.get("run_id") == run_id:
            matching_decisions.append(d)

    matching_decisions.sort(key=lambda d: (d.get("file_id", ""), d.get("timestamp", 0)))
    latest_by_file: dict[str, dict] = {}
    for d in matching_decisions:
        latest_by_file[d["file_key"]] = d
    decisions = list(latest_by_file.values())
    decisions.sort(key=lambda d: d.get("file_id", ""))

    invoices = [collect_invoice(store, d, rc.seleccion) for d in decisions]

    run_config_version = ""
    run_master_sha = ""
    timestamps = []
    for inv in invoices:
        snap = inv.get("snapshot", {})
        if not run_config_version and snap.get("config_version"):
            run_config_version = snap["config_version"]
        if not run_master_sha and snap.get("master_sha256"):
            run_master_sha = snap["master_sha256"]
        if inv.get("timestamp"):
            timestamps.append(inv["timestamp"])

    started = min(timestamps) if timestamps else None
    finished = max(timestamps) if timestamps else None

    counts = {k: 0 for k in ("PAGAR", "NO_PAGAR", "ESCALAR")}
    stats: dict[str, dict[str, Any]] = {}
    for inv in invoices:
        counts[inv["result"]] = counts.get(inv["result"], 0) + 1
        for e in inv["drivers"]:
            s = stats.setdefault(
                e["code"], {"code": e["code"], "total": 0, "FAIL": 0, "UNKNOWN": 0, "reasons": {}}
            )
            s["total"] += 1
            s[e["verdict"]] += 1
            if e["verdict"] == "UNKNOWN":
                cat = e.get("reason_code") or "OTRO"
                s["reasons"][cat] = s["reasons"].get(cat, 0) + 1
    rule_stats = []
    for s in sorted(stats.values(), key=lambda s: (-s["total"], s["code"])):
        s["reason_list"] = [
            (cat, _categoria(cat), n)
            for cat, n in sorted(s["reasons"].items(), key=lambda kv: (-kv[1], kv[0]))
        ]
        rule_stats.append(s)
    n_inv = len(invoices)
    total_ext = sum(inv["extraction_ms"] for inv in invoices)
    total_prs = sum(inv["parser_ms"] for inv in invoices)
    total_eval = sum(inv["evaluation_ms"] for inv in invoices)
    total_lat = sum(inv["total_ms"] for inv in invoices)
    avg_lat = round(total_lat / n_inv, 1) if n_inv > 0 else 0.0
    avg_ext = round(total_ext / n_inv, 1) if n_inv > 0 else 0.0
    avg_prs = round(total_prs / n_inv, 1) if n_inv > 0 else 0.0
    avg_eval = round(total_eval / n_inv, 1) if n_inv > 0 else 0.0
    return {
        "run_id": run_id,
        "config_version": run_config_version,
        "master_sha256": run_master_sha,
        "started": started,
        "started_iso": _dt(started),
        "finished_iso": _dt(finished),
        "generated_iso": datetime.now().astimezone().isoformat(timespec="seconds"),
        "counts": counts,
        "total": len(invoices),
        "rule_stats": rule_stats,
        "config_mismatch": bool(run_config_version and run_config_version != rc.version),
        "current_config_version": rc.version,
        "invoices": invoices,
        "metrics": {
            "total_ms": total_lat,
            "extraction_ms": total_ext,
            "parser_ms": total_prs,
            "evaluation_ms": total_eval,
            "avg_total_ms": avg_lat,
            "avg_extraction_ms": avg_ext,
            "avg_parser_ms": avg_prs,
            "avg_evaluation_ms": avg_eval,
        },
    }


# ------------------------------------------------------------------ render

_CSS = """
:root{--ok:#157347;--ok-bg:#e6f4ec;--bad:#b02a37;--bad-bg:#fbeaec;
--warn:#9a6700;--warn-bg:#fff4d5;--muted:#6c757d;--muted-bg:#f1f3f5;
--ink:#1c2430;--line:#dde3ea;--card:#ffffff;--bg:#f5f7fa;--accent:#1f4e79}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:1100px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:28px 0 10px;
border-bottom:2px solid var(--line);padding-bottom:6px}
h3{font-size:15px;margin:18px 0 6px}
a{color:var(--accent)}.muted{color:var(--muted)}
.badge{display:inline-block;padding:2px 10px;border-radius:999px;font-weight:600;
font-size:12.5px;white-space:nowrap}
.ok{background:var(--ok-bg);color:var(--ok)}.bad{background:var(--bad-bg);color:var(--bad)}
.warn{background:var(--warn-bg);color:var(--warn)}.muted-badge{background:var(--muted-bg);color:var(--muted)}
.cards{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 18px;min-width:130px}
.card .num{font-size:26px;font-weight:700}.card .lbl{font-size:12.5px;color:var(--muted)}
table{border-collapse:collapse;width:100%;background:var(--card);border:1px solid var(--line);
border-radius:8px;overflow:hidden;font-size:14px}
th,td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{background:#eef2f6;font-size:12.5px;text-transform:uppercase;letter-spacing:.04em;color:#4a5568}
tr:last-child td{border-bottom:none}tr.driver td{background:#fff8f0}
code,.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:13px}
pre{background:#0f1720;color:#d8e2ec;padding:12px;border-radius:8px;overflow:auto;font-size:12.5px}
.meta{display:flex;gap:18px;flex-wrap:wrap;color:var(--muted);font-size:13px;margin:6px 0 0}
.notice{border-left:4px solid var(--warn);background:var(--warn-bg);padding:10px 14px;border-radius:6px;margin:14px 0}
.driver-box{border-left:4px solid var(--accent);background:#eaf1f8;padding:10px 14px;border-radius:6px;margin:12px 0}
details{margin:6px 0}summary{cursor:pointer;color:var(--accent);font-size:13.5px}
.field-head{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}
.chip{display:inline-block;background:#eef2f6;border:1px solid var(--line);border-radius:6px;
padding:1px 8px;font-size:12px;font-family:ui-monospace,monospace}
footer{margin-top:40px;color:var(--muted);font-size:12.5px}
"""

_INDEX_TPL = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>filemaid · informe del run {{ run.run_id }}</title><style>{{ css }}</style></head>
<body><div class="wrap">
<h1>Informe de decisiones</h1>
<p class="muted">run <code>{{ run.run_id }}</code> · config <code>{{ run.config_version }}</code>
· maestro <code>{{ run.master_sha256[:16] }}…</code>
· inicio {{ run.started_iso }} · fin {{ run.finished_iso }}</p>
<p class="meta"><span>generado: {{ run.generated_iso }}</span></p>
{% if run.config_mismatch %}<div class="notice">⚠ El rules.yaml actual
(<code>{{ run.current_config_version }}</code>) no coincide con la config del run
(<code>{{ run.config_version }}</code>): los breadcrumbs de colapso se recalculan con la
config actual y pueden diferir de la decisión almacenada.</div>{% endif %}
<div class="cards">
<div class="card"><div class="num">{{ run.total }}</div><div class="lbl">facturas</div></div>
<div class="card"><div class="num ok-text">{{ run.counts.PAGAR }}</div><div class="lbl">PAGAR</div></div>
<div class="card"><div class="num">{{ run.counts.NO_PAGAR }}</div><div class="lbl">NO_PAGAR</div></div>
<div class="card"><div class="num">{{ run.counts.ESCALAR }}</div><div class="lbl">ESCALAR</div></div>
<div class="card"><div class="num">{{ run.metrics.avg_total_ms }} <span style="font-size:14px;font-weight:normal">ms</span></div><div class="lbl">latencia media / factura</div></div>
<div class="card"><div class="num" style="font-size:18px;margin-top:6px">{{ run.metrics.avg_extraction_ms }} <span style="font-size:12px;color:var(--muted)">ms</span> · {{ run.metrics.avg_parser_ms }} <span style="font-size:12px;color:var(--muted)">ms</span> · {{ run.metrics.avg_evaluation_ms }} <span style="font-size:12px;color:var(--muted)">ms</span></div><div class="lbl">extracción · parser · reglas (media)</div></div>
</div>
{% if run.rule_stats %}
<h2>Errores comunes (reglas que deciden)</h2>
<table><thead><tr><th>regla</th><th>decide en</th><th>FAIL</th><th>UNKNOWN</th>
<th>tipos de UNKNOWN</th></tr></thead><tbody>
{% for s in run.rule_stats %}
<tr><td><code>{{ s.code }}</code></td>
<td><strong>{{ s.total }}</strong> de {{ run.total }}</td>
<td>{% if s.FAIL %}<span class="badge bad">{{ s.FAIL }}</span>{% else %}<span class="muted">0</span>{% endif %}</td>
<td>{% if s.UNKNOWN %}<span class="badge warn">{{ s.UNKNOWN }}</span>{% else %}<span class="muted">0</span>{% endif %}</td>
<td>{% for cat, label, n in s.reason_list %}<span class="chip">{{ label }} × {{ n }}</span> {% else %}
<span class="muted">—</span>{% endfor %}</td>
</tr>{% endfor %}</tbody></table>
<p class="muted">FAIL resuelve al resultado configurado (<code>outcomes.on_fail</code>):
NO_PAGAR = negativo definitivo, inmune a juicio humano · ESCALAR = duda razonable
(escalar antes que pagar) · UNKNOWN siempre ESCALAR. Los tipos de UNKNOWN son códigos
estables
(<code>SIN_CAMPO</code>, <code>SIN_CANDIDATO_VALIDO</code>, <code>CONFIANZA_BAJA</code>,
<code>NO_PARSEABLE</code>, <code>CRUZ_NO_POSIBLE</code>) guardados en el store.</p>
{% endif %}
<table><thead><tr><th>file_id</th><th>resultado</th><th>reglas que deciden</th>
<th>PASS</th><th>FAIL</th><th>UNKNOWN</th><th>latencia</th><th>desglose (ext/prs/reg)</th><th></th></tr></thead><tbody>
{% for inv in run.invoices %}
<tr><td class="mono">{{ inv.file_id }}</td>
<td><span class="badge {{ inv.result_class }}">{{ inv.result }}</span></td>
<td>{% for e in inv.drivers %}<span class="chip">{{ e.code }}</span> {% else %}
<span class="muted">{{ inv.driver_kind }}</span>{% endfor %}</td>
<td>{{ inv.counts.PASS }}</td><td>{{ inv.counts.FAIL }}</td><td>{{ inv.counts.UNKNOWN }}</td>
<td class="mono"><strong>{{ inv.total_ms }} ms</strong></td>
<td class="muted mono" style="font-size:12px">{{ inv.extraction_ms }} · {{ inv.parser_ms }} · {{ inv.evaluation_ms }} ms</td>
<td><a href="facturas/{{ inv.scan_id }}.html">detalle →</a></td></tr>
{% endfor %}</tbody></table>
<footer>filemaid · informe estático generado desde PouchDB. Los breadcrumbs
del colapso se recomputan con <code>escoger</code>: determinista y auditable.</footer>
</div></body></html>
"""

_INVOICE_TPL = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ inv.file_id }} · {{ inv.result }}</title><style>{{ css }}</style></head>
<body><div class="wrap">
<p><a href="../index.html">← índice del run</a></p>
<h1 class="mono">{{ inv.file_id }}</h1>
<p><span class="badge {{ inv.result_class }}">{{ inv.result }}</span></p>
<p class="meta"><span>invoice_id: <code>{{ inv.invoice_id }}</code></span>
<span>sha256: <code>{{ inv.sha256[:16] }}…</code></span>
<span>run: <code>{{ inv.run_id }}</code></span>
<span>decidido: {{ inv.timestamp_iso }}</span></p>
<div class="cards">
<div class="card"><div class="num">{{ inv.total_ms }} <span style="font-size:14px;font-weight:normal">ms</span></div><div class="lbl">latencia total</div></div>
<div class="card"><div class="num">{{ inv.extraction_ms }} <span style="font-size:14px;font-weight:normal">ms</span></div><div class="lbl">extracción (escalera)</div></div>
<div class="card"><div class="num">{{ inv.parser_ms }} <span style="font-size:14px;font-weight:normal">ms</span></div><div class="lbl">parser (candidatos)</div></div>
<div class="card"><div class="num">{{ inv.evaluation_ms }} <span style="font-size:14px;font-weight:normal">ms</span></div><div class="lbl">evaluación de reglas</div></div>
</div>

<div class="driver-box"><strong>{{ inv.result }}</strong> — {{ inv.driver_kind }}.
{% if inv.drivers %}{% for e in inv.drivers %}<span class="chip">{{ e.code }}</span> {% endfor %}
{% endif %}</div>

<h2>Reglas evaluadas ({{ inv.evaluations | length }})</h2>
<table><thead><tr><th>veredicto</th><th>regla</th><th>motivo</th><th>valores consumidos</th></tr></thead><tbody>
{% for e in inv.evaluations %}
<tr class="{{ 'driver' if e.is_driver else '' }}">
<td><span class="badge {{ e.verdict_class }}">{{ e.verdict }}</span>
{% if e.reason_label %}<span class="badge warn">{{ e.reason_label }}</span>{% endif %}</td>
<td><code>{{ e.code }}</code></td>
<td>{{ e.reason }}</td>
<td>{% if e.consumed_pairs %}{% for k, v in e.consumed_pairs %}
<span class="chip">{{ k }} = {{ v }}</span> {% endfor %}{% else %}<span class="muted">—</span>{% endif %}</td>
</tr>{% endfor %}</tbody></table>

<h2>Breadcrumbs de campos ({{ inv.fields | length }})</h2>
<p class="muted">Todos los candidatos extraídos y su suerte en el colapso determinista
(<code>escoger</code>): puntuación = confianza × peso del extractor.</p>
{% for f in inv.fields %}
<h3 class="field-head" id="campo-{{ f.type }}"><code>{{ f.type }}</code>
{% if f.chosen %}<span class="badge ok">elegido: {{ f.chosen.value }}</span>
<span class="muted">{{ f.chosen.why }}</span>
{% else %}<span class="badge warn">sin candidato fiable</span>
{% if f.collapse_label %}<span class="badge warn">{{ f.collapse_label }}</span>{% endif %}
<span class="muted">{{ f.collapse_reason }}</span>{% endif %}</h3>
{% if f.candidates %}
<table><thead><tr><th>estado</th><th>extractor</th><th>valor</th><th>confianza</th><th>peso</th>
<th>puntuación</th><th>motivo</th></tr></thead><tbody>
{% for c in f.candidates %}
<tr><td><span class="badge {{ c.status_class }}">{{ c.status or '—' }}</span></td>
<td><code>{{ c.extractor }}</code></td><td class="mono">{{ c.value }}</td>
<td>{{ '%.2f' | format(c.confidence) }}</td><td>{{ '%.2f' | format(c.weight) }}</td>
<td>{% if c.score is not none %}{{ '%.3f' | format(c.score) }}{% else %}<span class="muted">no puntúa</span>{% endif %}</td>
<td class="muted">{{ c.reason }}</td></tr>{% endfor %}</tbody></table>
<p class="muted">tests de formato: {% for t in f.format_tests %}<span class="chip">{{ t }}</span> {% endfor %}
· umbral de puntuación: {{ '%.2f' | format(f.score_threshold) }}</p>
{% else %}<p class="muted">sin candidatos en el store</p>{% endif %}
{% endfor %}

{% if inv.pages %}
<h2>Extracción (escalera por página)</h2>
{% for p in inv.pages %}
<h3>página {{ p.page if p.page is not none else '—' }}</h3>
<table><thead><tr><th>escalón</th><th>resultado</th><th>confianza</th><th>latencia</th><th>versión</th></tr></thead><tbody>
{% for r in p.rungs %}
<tr><td><code>{{ r.stage }}</code></td>
<td>{% if r.skipped %}<span class="badge warn">{{ r.outcome }}</span>
{% else %}<code>{{ r.outcome }}</code>{% endif %}</td>
<td>{% if r.confidence is not none %}{{ '%.2f' | format(r.confidence) }}{% else %}<span class="muted">—</span>{% endif %}</td>
<td>{{ r.latency_ms }} ms</td><td class="muted mono">{{ r.extractor_version }}</td></tr>
{% endfor %}</tbody></table>
{% endfor %}{% endif %}

<h2>Snapshot de configuración</h2>
<details><summary>thresholds, versiones de extractores y maestro activos en la decisión</summary>
<pre>{{ snapshot_json }}</pre></details>
<details><summary>JSON completo de este informe</summary><pre>{{ report_json }}</pre></details>
<footer>filemaid · informe estático · generado {{ generated_iso }}</footer>
</div></body></html>
"""


def write_report(store: PouchStore, cfg: AppConfig, run_id: str, out_dir: Path) -> Path:
    """Escribe index.html + facturas/<scan_id>.html."""
    env = Environment(autoescape=True)
    report = collect_run(store, cfg, run_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    facturas_dir = out_dir / "facturas"
    facturas_dir.mkdir(exist_ok=True)

    index = env.from_string(_INDEX_TPL).render(run=report, css=_CSS)
    (out_dir / "index.html").write_text(index, encoding="utf-8")

    tpl = env.from_string(_INVOICE_TPL)
    for inv in report["invoices"]:
        page = tpl.render(
            inv=inv,
            css=_CSS,
            snapshot_json=json.dumps(
                inv["snapshot"], ensure_ascii=False, indent=2, sort_keys=True
            ),
            report_json=json.dumps(inv, ensure_ascii=False, indent=2, sort_keys=True),
            generated_iso=report["generated_iso"],
        )
        (facturas_dir / f"{inv['scan_id']}.html").write_text(page, encoding="utf-8")
        if inv.get("scan_id"):
            archive_output(
                cfg.root, inv["scan_id"], facturas_dir / f"{inv['scan_id']}.html", "text/html"
            )
    for inv in report["invoices"]:
        if inv.get("scan_id"):
            archive_output(cfg.root, inv["scan_id"], out_dir / "index.html", "text/html")
    return out_dir
