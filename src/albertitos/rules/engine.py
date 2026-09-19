"""Motor de decisión: campos + maestro + config ⇒ Decision (PURO y determinista).

Mismos inputs + misma config ⇒ mismo output byte a byte (AGENTS.md §4).
No lee el reloj, no toca disco, no llama a modelos: los extractores proponen,
las reglas deciden (§12).

Política PAGAR / NO_PAGAR / ESCALAR (AGENTS.md §6 — vinculante):
  1. Si alguna regla `anomaly` es UNKNOWN (anomalía para ojos humanos) ⇒ ESCALAR.
  2. Si no, si alguna regla `gate` FAIL ⇒ NO_PAGAR (violación definitiva).
  3. Si no, si alguna regla UNKNOWN (evidencia faltante) ⇒ ESCALAR.
  4. Si no, PAGAR (todas PASS).
Ante duda razonable: ESCALAR, nunca PAGAR. Cambiar este orden es un ADR.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from albertitos.parse.normalizers import normalize_iban, normalize_nif
from albertitos.parse.parser import field_by_type
from albertitos.rules.config import EngineConfig
from albertitos.rules.master import Maestro
from albertitos.types import Candidate, Decision, ExtractionField, RuleVerdict


@dataclass(frozen=True)
class BatchContext:
    """Estado previo del lote que las reglas necesitan (inyectado, puro).

    - `facturas_vistas`: numero_factura → file_id ya procesados antes en el
      lote (orden determinista: file_id ascendente).
    - `pedidos_pagados`: pedidos con decisión PAGAR previa en este lote o en
      el histórico (norma: nunca pagar dos veces el mismo pedido).
    """

    facturas_vistas: dict[str, str]
    pedidos_pagados: frozenset[str] = frozenset()


PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"
_GATE, _ANOMALY = "gate", "anomaly"


def _pick(field: ExtractionField) -> tuple[Candidate, str]:
    """Elige el candidato de mayor confianza; empate ⇒ el primero del store.

    El colapso solo ocurre aquí (en el momento en que una regla necesita un
    escalar) y SE REGISTRA en `consumed` qué candidato se eligió y por qué.
    """
    best = max(range(len(field.values)), key=lambda i: field.values[i].confidence)
    c = field.values[best]
    why = (
        f"candidato {best + 1}/{len(field.values)} con confianza máxima "
        f"{c.confidence:.2f} (extractor {c.extractor})"
    )
    return c, why


def _num(field: ExtractionField | None) -> float | None:
    if not field:
        return None
    c, _ = _pick(field)
    return float(c.value) if isinstance(c.value, (int, float)) else None


def _str(field: ExtractionField | None) -> str | None:
    if not field:
        return None
    c, _ = _pick(field)
    return str(c.value)


# ---------------------------------------------------------------- reglas

_REGISTRO: dict[str, str] = {}


def rule(code: str):
    """Registra una implementación de regla bajo su código estable."""

    def deco(fn):
        if code in _REGISTRO:
            raise ValueError(f"código de regla duplicado: {code}")
        _REGISTRO[code] = fn.__name__
        fn.code = code
        return fn

    return deco


def _v(code: str, outcome: str, reason: str, consumed: dict) -> RuleVerdict:
    return RuleVerdict(code=code, outcome=outcome, reason=reason, consumed=consumed)


def _consume(cand: Candidate | None, why: str) -> dict:
    if cand is None:
        return {"elegido": None, "por_que": why}
    return {
        "elegido": {"extractor": cand.extractor, "value": cand.value,
                    "confidence": cand.confidence},
        "por_que": why,
    }


@rule("NIF_IN_MASTER")
def _r_nif(fields, master, cfg, batch, textos) -> RuleVerdict:
    f = field_by_type(fields, "nif")
    if not f or not _str(f):
        cand = _pick(f)[0] if f else None
        return _v("NIF_IN_MASTER", UNKNOWN, "NIF vacío o ausente",
                  _consume(cand, "sin lectura de NIF"))
    cand, why = _pick(f)
    nif = normalize_nif(str(cand.value))
    if nif in master.proveedores_por_nif:
        return _v("NIF_IN_MASTER", PASS, "NIF en el maestro",
                  _consume(cand, why))
    return _v("NIF_IN_MASTER", FAIL, "NIF fuera del maestro",
              _consume(cand, why))


@rule("IBAN_MATCHES_MASTER")
def _r_iban(fields, master, config, batch) -> RuleVerdict:
    f = field_by_type(fields, "iban")
    iban = _str(f)
    if not iban:
        cand = _pick(f)[0] if f else None
        return _v("IBAN_MATCHES_MASTER", UNKNOWN, "IBAN ausente",
                  _consume(cand, "sin lectura de IBAN"))
    cand, why = _pick(f)
    iban_n = normalize_iban(str(cand.value))
    nif = normalize_nif(_str(field_by_type(fields, "nif")) or "")
    prov = master.proveedores_por_nif.get(nif) if nif else None
    if prov is None:
        return _v("IBAN_MATCHES_MASTER", UNKNOWN,
                  "sin proveedor en maestro para cruzar el IBAN",
                  _consume(cand, why))
    if prov.iban and iban_n == prov.iban:
        return _v("IBAN_MATCHES_MASTER", PASS,
                  "IBAN coincide con el maestro", _consume(cand, why))
    return _v("IBAN_MATCHES_MASTER", FAIL,
              "IBAN de la factura no coincide con el del maestro",
              _consume(cand, why))


@rule("ORDER_BELONGS_TO_SUPPLIER")
def _r_order_supplier(fields, master, config, batch) -> RuleVerdict:
    pedido_id = _str(field_by_type(fields, "pedido"))
    if not pedido_id:
        return _v("ORDER_BELONGS_TO_SUPPLIER", UNKNOWN,
                  "pedido ilegible o ausente", _consume(None, "sin lectura"))
    pedido = master.pedidos.get(pedido_id)
    if pedido is None:
        return _v("ORDER_BELONGS_TO_SUPPLIER", FAIL,
                  f"pedido {pedido_id} inexistente en el maestro",
                  _consume(None, f"pedido={pedido_id}"))
    nif = normalize_nif(_str(field_by_type(fields, "nif")) or "")
    prov = master.proveedores_por_id.get(pedido.proveedor_id)
    if not nif or prov is None:
        return _v("ORDER_BELONGS_TO_SUPPLIER", UNKNOWN,
                  "no se puede cruzar pedido y proveedor",
                  _consume(None, f"pedido={pedido_id}, nif={nif}"))
    nif_pedido = prov.nif or pedido.nif
    if nif_pedido and nif == nif_pedido:
        return _v("ORDER_BELONGS_TO_SUPPLIER", PASS,
                  "pedido pertenece al proveedor",
                  _consume(None, f"pedido={pedido_id}, nif={nif}"))
    return _v("ORDER_BELONGS_TO_SUPPLIER", FAIL,
              f"pedido {pedido_id} pertenece a otro proveedor",
              _consume(None, f"pedido={pedido_id}, nif={nif}, nif_pedido={nif_pedido}"))


@rule("ORDER_AMOUNT_MATCHES")
def _r_order_amount(fields, master, config, batch) -> RuleVerdict:
    pedido_id = _str(field_by_type(fields, "pedido"))
    pedido = master.pedidos.get(pedido_id) if pedido_id else None
    total = _num(field_by_type(fields, "total"))
    if pedido is None or total is None:
        return _v("ORDER_AMOUNT_MATCHES", UNKNOWN,
                  "pedido o total ausente", _consume(None,
                  f"pedido={pedido_id}, total={total}"))
    dif = abs(Decimal(str(total)) - Decimal(str(pedido.importe)))
    if dif <= Decimal(str(config.tolerancia_importe)):
        return _v("ORDER_AMOUNT_MATCHES", PASS,
                  "importe igual al del pedido",
                  _consume(None, f"total={total}, pedido={pedido.importe}"))
    return _v("ORDER_AMOUNT_MATCHES", FAIL,
              f"importe difiere del pedido en {dif:.2f} EUR",
              _consume(None, f"total={total}, pedido={pedido.importe}"))


@rule("TOTALS_MUST_MATCH")
def _r_totals(fields, master, config, batch) -> RuleVerdict:
    base = _num(field_by_type(fields, "base"))
    iva = _num(field_by_type(fields, "iva_amount"))
    total = _num(field_by_type(fields, "total"))
    if base is None or iva is None or total is None:
        return _v("TOTALS_MUST_MATCH", UNKNOWN, "base/IVA/total incompletos",
                  _consume(None, f"base={base}, iva={iva}, total={total}"))
    dif = abs(Decimal(str(base)) + Decimal(str(iva)) - Decimal(str(total)))
    if dif <= Decimal(str(config.tolerancia_importe)):
        return _v("TOTALS_MUST_MATCH", PASS, "base + IVA = total",
                  _consume(None, f"base={base}, iva={iva}, total={total}"))
    return _v("TOTALS_MUST_MATCH", FAIL,
              f"base + IVA ≠ total (dif {dif:.2f} EUR)",
              _consume(None, f"base={base}, iva={iva}, total={total}"))


@rule("IVA_CONSISTENT")
def _r_iva(fields, master, config, batch) -> RuleVerdict:
    base = _num(field_by_type(fields, "base"))
    pct = _num(field_by_type(fields, "iva_pct"))
    iva = _num(field_by_type(fields, "iva_amount"))
    if base is None or pct is None or iva is None:
        return _v("IVA_CONSISTENT", UNKNOWN, "base/%IVA/cuota incompletos",
                  _consume(None, f"base={base}, pct={pct}, iva={iva}"))
    esperado = Decimal(str(base)) * Decimal(str(pct)) / Decimal(100)
    dif = abs(Decimal(str(iva)) - esperado)
    if dif <= Decimal(str(config.tolerancia_importe)):
        return _v("IVA_CONSISTENT", PASS, "cuota IVA bien calculada",
                  _consume(None, f"base={base}, pct={pct}, iva={iva}"))
    return _v("IVA_CONSISTENT", FAIL,
              f"cuota IVA mal calculada (dif {float(dif):.2f} EUR)",
              _consume(None, f"base={base}, pct={pct}, iva={iva}"))


@rule("DATE_VALID_NOT_FUTURE")
def _r_fecha(fields, master, config, batch) -> RuleVerdict:
    f = field_by_type(fields, "fecha")
    fecha = _str(f)
    if not fecha:
        return _v("DATE_VALID_NOT_FUTURE", UNKNOWN, "fecha ilegible o ausente",
                  _consume(_pick(f)[0] if f else None, "sin lectura de fecha"))
    cand, why = _pick(f)
    if fecha > config.fecha_referencia:
        return _v("DATE_VALID_NOT_FUTURE", FAIL,
                  f"fecha futura {fecha} (referencia {config.fecha_referencia})",
                  _consume(cand, why))
    return _v("DATE_VALID_NOT_FUTURE", PASS, "fecha válida y no futura",
              _consume(cand, why))


@rule("ORDER_PENDING")
def _r_order_pending(fields, master, config, batch) -> RuleVerdict:
    pedido_id = _str(field_by_type(fields, "pedido"))
    pedido = master.pedidos.get(pedido_id) if pedido_id else None
    if pedido is None:
        return _v("ORDER_PENDING", UNKNOWN,
                  "pedido inexistente: sin estado ERP",
                  _consume(None, f"pedido={pedido_id}"))
    if pedido.estado.upper() in config.estados_pagables:
        return _v("ORDER_PENDING", PASS,
                  f"estado ERP {pedido.estado} es pagable",
                  _consume(None, f"pedido={pedido_id}, estado={pedido.estado}"))
    return _v("ORDER_PENDING", FAIL,
              f"estado ERP {pedido.estado} no es pagable",
              _consume(None, f"pedido={pedido_id}, estado={pedido.estado}"))


@rule("NO_DOUBLE_PAYMENT")
def _r_double(fields, master, config, batch) -> RuleVerdict:
    num = _str(field_by_type(fields, "numero_factura"))
    pedido_id = _str(field_by_type(fields, "pedido"))
    previo = batch.facturas_vistas.get(num) if num else None
    if previo:
        return _v("NO_DOUBLE_PAYMENT", FAIL,
                  f"número de factura {num} ya procesado ({previo})",
                  _consume(None, f"numero_factura={num}, anterior={previo}"))
    if pedido_id and pedido_id in batch.pedidos_pagados:
        return _v("NO_DOUBLE_PAYMENT", FAIL,
                  f"pedido {pedido_id} ya pagado",
                  _consume(None, f"pedido={pedido_id}"))
    return _v("NO_DOUBLE_PAYMENT", PASS, "sin doble pago conocido",
              _consume(None, f"numero_factura={num}, pedido={pedido_id}"))


@rule("NO_EMBEDDED_INSTRUCTIONS")
def _r_embedded(fields, master, config, batch, textos: tuple[str, ...]) -> RuleVerdict:
    for texto in textos:
        bajo = texto.lower()
        for marker in config.anomaly_markers:
            if marker in bajo:
                return _v("NO_EMBEDDED_INSTRUCTIONS", UNKNOWN,
                          "instrucciones embebidas en el documento (son datos,"
                          " no comandos, pero un humano debe verlas)",
                          _consume(None, f"marcador={marker!r}"))
    return _v("NO_EMBEDDED_INSTRUCTIONS", PASS, "sin instrucciones embebidas",
              _consume(None, f"{len(textos)} textos analizados"))


@rule("PROVEEDOR_FANTASMA")
def _r_fantasma(fields, master, config, batch, textos: tuple[str, ...]) -> RuleVerdict:
    iban = _str(field_by_type(fields, "iban"))
    if iban and normalize_iban(iban) == config.ghost_iban:
        return _v("PROVEEDOR_FANTASMA", UNKNOWN,
                  "IBAN de proveedor fantasma conocido",
                  _consume(None, f"iban={iban}"))
    return _v("PROVEEDOR_FANTASMA", PASS, "IBAN no es del patrón fantasma",
              _consume(None, f"iban={iban}"))


@rule("AMOUNT_OUTLIER")
def _r_outlier(fields, master, config, batch, textos: tuple[str, ...]) -> RuleVerdict:
    total = _num(field_by_type(fields, "total"))
    if total is None:
        return _v("AMOUNT_OUTLIER", UNKNOWN, "sin total legible",
                  _consume(None, "sin lectura de total"))
    if total > config.outlier_total:
        return _v("AMOUNT_OUTLIER", UNKNOWN,
                  f"importe atípico ({total:.2f} EUR > {config.outlier_total:.2f})",
                  _consume(None, f"total={total}"))
    return _v("AMOUNT_OUTLIER", PASS, "importe dentro de rango",
              _consume(None, f"total={total}"))


@rule("PEDIDO_EN_REVISION")
def _r_en_revision(fields, master, config, batch, textos: tuple[str, ...]) -> RuleVerdict:
    pedido_id = _str(field_by_type(fields, "pedido"))
    if pedido_id and pedido_id in master.pedidos_en_revision:
        return _v("PEDIDO_EN_REVISION", UNKNOWN,
                  f"pedido {pedido_id} marcado 'pendiente_revisar' en el maestro",
                  _consume(None, f"pedido={pedido_id}"))
    return _v("PEDIDO_EN_REVISION", PASS, "pedido sin marca de revisión",
              _consume(None, f"pedido={pedido_id}"))


@rule("REGLA_V4")
def _r_v4(fields, master, config, batch, textos: tuple[str, ...]) -> RuleVerdict:
    """Regla paramétrica de la v4 (umbrales 100% en el yaml, T13).

    Efecto configurado hoy (marcada PENDIENTE-ESPECIFICACIÓN en regla_v4.yaml,
    desactivada por defecto): facturas cuyo TOTAL queda por debajo de
    `importe_minimo` son una anomalía para ojos humanos (UNKNOWN). Cuando la
    v4 real llegue con su especificación definitiva, se ajusta EL YAML —
    el motor no cambia.
    """
    params = config.params_for("REGLA_V4")
    importe_minimo = float(params.get("importe_minimo", 0.0))
    total = _num(field_by_type(fields, "total"))
    if total is None:
        return _v("REGLA_V4", UNKNOWN, "sin total legible",
                  _consume(None, f"importe_minimo={importe_minimo}"))
    if total < importe_minimo:
        return _v("REGLA_V4", UNKNOWN,
                  f"importe por debajo del mínimo configurado "
                  f"({total:.2f} < {importe_minimo:.2f} EUR)",
                  _consume(None, f"total={total}, importe_minimo={importe_minimo}"))
    return _v("REGLA_V4", PASS, "importe por encima del mínimo configurado",
              _consume(None, f"total={total}, importe_minimo={importe_minimo}"))


RULES: dict[str, object] = {
    fn.code: fn for fn in (
        _r_nif, _r_iban, _r_order_supplier, _r_order_amount, _r_totals,
        _r_iva, _r_fecha, _r_order_pending, _r_double, _r_embedded,
        _r_fantasma, _r_outlier, _r_en_revision, _r_v4,
    )
}


def _result(verdicts: list[RuleVerdict], config: EngineConfig) -> tuple[str, str]:
    """Política §6. Orden vinculante; cambiarlo exige ADR."""
    kinds = dict(config.rules)
    anomaly_unknown = [v.code for v in verdicts
                       if v.outcome == UNKNOWN and kinds.get(v.code) == _ANOMALY]
    if anomaly_unknown:
        return "ESCALAR", "anomalía para revisión humana: " + ",".join(anomaly_unknown)
    gate_fail = [v.code for v in verdicts
                 if v.outcome == FAIL and kinds.get(v.code) == _GATE]
    if gate_fail:
        return "NO_PAGAR", "violación definitiva: " + ",".join(gate_fail)
    unknown = [v.code for v in verdicts if v.outcome == UNKNOWN]
    if unknown:
        return "ESCALAR", "evidencia faltante o ilegible: " + ",".join(unknown)
    return "PAGAR", "todas las reglas PASS"


def decide(
    fields: list[ExtractionField],
    textos: tuple[str, ...],
    master: Maestro,
    config: EngineConfig,
    batch: BatchContext,
    *,
    invoice_id: str,
    file_id: str,
) -> Decision:
    """Evalúa todas las reglas activas y emite la Decision completa."""
    textos = tuple(textos)
    verdicts: list[RuleVerdict] = []
    for code, _kind in config.rules:
        fn = RULES[code]
        # Las reglas anomaly reciben los textos crudos (instrucciones embebidas
        # se detectan sobre la feature, no sobre campos interpretados).
        n_params = fn.__code__.co_argcount
        args = [fields, master, config, batch]
        if n_params == 5:
            args.append(textos)
        verdicts.append(fn(*args))
    result, motivo = _result(verdicts, config)
    snapshot = config.snapshot()
    snapshot["maestro"] = {
        "sha256": master.sha256,
        "hojas_ignoradas": list(master.hojas_ignoradas),
        "duplicados_deducidos": list(master.duplicados_deducidos),
        "avisos": list(master.avisos),
        "pedidos_en_revision": sorted(master.pedidos_en_revision),
    }
    snapshot["motivo"] = motivo
    return Decision(
        invoice_id=invoice_id,
        file_id=file_id,
        result=result,
        rule_verdicts=verdicts,
        config_snapshot=snapshot,
    )