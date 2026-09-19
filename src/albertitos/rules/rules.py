"""Las reglas (códigos estables). FAIL ⇒ NO_PAGAR; UNKNOWN ⇒ ESCALAR.

Fuente normativa: docs/normas.md. La regla base de oro: ante duda razonable,
escalar antes que pagar.
"""

from __future__ import annotations

from datetime import date

from albertitos.parse.normalizers import amounts_match
from albertitos.types import RuleVerdict

from .base import RuleContext, RuleEvaluation

TOLERANCE_EUR = 0.01


def _ev(code: str, verdict: RuleVerdict, reason: str, consumed: dict, chosen: dict[str, str] | None = None) -> RuleEvaluation:
    return RuleEvaluation(code=code, verdict=verdict, reason=reason, consumed=consumed, chosen_candidates=chosen or {})


class NifInMaster:
    code = "NIF_IN_MASTER"

    def evaluate(self, ctx: RuleContext) -> RuleEvaluation:
        cand, why = ctx.pick("nif", ctx.threshold(self.code, "min_confidence", 0.7))
        if cand is None:
            return _ev(self.code, RuleVerdict.UNKNOWN, f"NIF no fiable: {why}", {})
        in_master = cand.value in ctx.master.proveedores
        return _ev(
            self.code,
            RuleVerdict.PASS if in_master else RuleVerdict.FAIL,
            f"NIF {cand.value} {'está' if in_master else 'NO está'} en el maestro",
            {"nif": str(cand.value)},
            {"nif": f"{cand.extractor}@{cand.confidence:.2f} (mayor confianza)"},
        )


class IbanMatchesMaster:
    code = "IBAN_MATCHES_MASTER"

    def evaluate(self, ctx: RuleContext) -> RuleEvaluation:
        iban, why_iban = ctx.pick("iban", ctx.threshold(self.code, "min_confidence", 0.7))
        nif, why_nif = ctx.pick("nif", 0.7)
        if iban is None or nif is None:
            return _ev(self.code, RuleVerdict.UNKNOWN, f"datos no fiables: {why_iban or why_nif}", {})
        prov = ctx.master.proveedores.get(str(nif.value))
        if prov is None:
            return _ev(self.code, RuleVerdict.UNKNOWN, "NIF fuera de maestro: no hay IBAN con qué cruzar", {})
        ok = str(iban.value) == prov.iban
        return _ev(
            self.code,
            RuleVerdict.PASS if ok else RuleVerdict.FAIL,
            f"IBAN {iban.value} {'coincide' if ok else 'NO coincide'} con el maestro de {nif.value}",
            {"iban": str(iban.value), "nif": str(nif.value), "master_iban": prov.iban},
            {"iban": f"{iban.extractor}@{iban.confidence:.2f}", "nif": f"{nif.extractor}@{nif.confidence:.2f}"},
        )


class OrderBelongsToSupplier:
    code = "ORDER_BELONGS_TO_SUPPLIER"

    def evaluate(self, ctx: RuleContext) -> RuleEvaluation:
        pedido, why_p = ctx.pick("pedido", ctx.threshold(self.code, "min_confidence", 0.7))
        nif, why_n = ctx.pick("nif", 0.7)
        total, why_t = ctx.pick("total", 0.7)
        if pedido is None or nif is None or total is None:
            return _ev(self.code, RuleVerdict.UNKNOWN, f"datos no fiables: {why_p or why_n or why_t}", {})
        order = ctx.master.pedidos.get(str(pedido.value))
        if order is None:
            return _ev(self.code, RuleVerdict.FAIL, f"Pedido {pedido.value} no existe en el ERP", {"pedido": str(pedido.value)})
        belongs = order.nif_proveedor == str(nif.value)
        amount_ok = amounts_match(float(total.value), order.importe, TOLERANCE_EUR)
        if not belongs:
            return _ev(
                self.code, RuleVerdict.FAIL,
                f"Pedido {order.numero} pertenece a {order.nif_proveedor}, no a {nif.value}",
                {"pedido": order.numero, "nif": str(nif.value)},
            )
        if not amount_ok:
            return _ev(
                self.code, RuleVerdict.FAIL,
                f"Importe factura {total.value} ≠ importe pedido {order.importe} (tol {TOLERANCE_EUR} EUR)",
                {"total": float(total.value), "pedido_importe": order.importe},
            )
        return _ev(
            self.code, RuleVerdict.PASS,
            f"Pedido {order.numero} existe, es de {nif.value} y los importes cuadran",
            {"pedido": order.numero, "total": float(total.value)},
            {"pedido": f"{pedido.extractor}@{pedido.confidence:.2f}", "total": f"{total.extractor}@{total.confidence:.2f}"},
        )


class OrderPending:
    code = "ORDER_PENDING"

    def evaluate(self, ctx: RuleContext) -> RuleEvaluation:
        pedido, why = ctx.pick("pedido", ctx.threshold(self.code, "min_confidence", 0.7))
        if pedido is None:
            return _ev(self.code, RuleVerdict.UNKNOWN, f"pedido no fiable: {why}", {})
        order = ctx.master.pedidos.get(str(pedido.value))
        if order is None:
            return _ev(self.code, RuleVerdict.UNKNOWN, "pedido no existe en el ERP: no hay estado", {"pedido": str(pedido.value)})
        ok = order.estado == "PENDIENTE"
        return _ev(
            self.code,
            RuleVerdict.PASS if ok else RuleVerdict.FAIL,
            f"Estado ERP del pedido {order.numero}: {order.estado}",
            {"estado": order.estado},
            {"pedido": f"{pedido.extractor}@{pedido.confidence:.2f}"},
        )


class NoDoublePayment:
    code = "NO_DOUBLE_PAYMENT"

    def evaluate(self, ctx: RuleContext) -> RuleEvaluation:
        pedido, why = ctx.pick("pedido", ctx.threshold(self.code, "min_confidence", 0.7))
        if pedido is None:
            return _ev(self.code, RuleVerdict.UNKNOWN, f"pedido no fiable: {why}", {})
        order = ctx.master.pedidos.get(str(pedido.value))
        if order is None:
            return _ev(self.code, RuleVerdict.UNKNOWN, "pedido no existe en el ERP", {"pedido": str(pedido.value)})
        if order.pagado:
            return _ev(self.code, RuleVerdict.FAIL, f"Pedido {order.numero} ya está pagado: nunca pagar dos veces", {"pagado": True})
        return _ev(self.code, RuleVerdict.PASS, f"Pedido {order.numero} sin pago previo", {"pagado": False})


class IvaConsistent:
    code = "IVA_CONSISTENT"

    def evaluate(self, ctx: RuleContext) -> RuleEvaluation:
        base, why_b = ctx.pick("base", ctx.threshold(self.code, "min_confidence", 0.6))
        iva, why_i = ctx.pick("iva_amount", 0.6)
        rate, why_r = ctx.pick("iva_rate", 0.6)
        if base is None or iva is None or rate is None:
            return _ev(self.code, RuleVerdict.UNKNOWN, f"datos no fiables: {why_b or why_i or why_r}", {})
        expected = round(float(base.value) * float(rate.value) / 100.0, 2)
        ok = amounts_match(float(iva.value), expected, TOLERANCE_EUR)
        return _ev(
            self.code,
            RuleVerdict.PASS if ok else RuleVerdict.FAIL,
            f"IVA reportado {iva.value} vs {rate.value}% de base {base.value} = {expected}",
            {"base": float(base.value), "iva": float(iva.value), "rate": float(rate.value), "esperado": expected},
            {"base": f"{base.extractor}@{base.confidence:.2f}", "iva_amount": f"{iva.extractor}@{iva.confidence:.2f}"},
        )


class TotalsMustMatch:
    code = "TOTALS_MUST_MATCH"

    def evaluate(self, ctx: RuleContext) -> RuleEvaluation:
        total, why_t = ctx.pick("total", ctx.threshold(self.code, "min_confidence", 0.7))
        base, why_b = ctx.pick("base", 0.6)
        iva, why_i = ctx.pick("iva_amount", 0.6)
        if total is None or base is None or iva is None:
            return _ev(self.code, RuleVerdict.UNKNOWN, f"datos no fiables: {why_t or why_b or why_i}", {})
        expected = round(float(base.value) + float(iva.value), 2)
        ok = amounts_match(float(total.value), expected, TOLERANCE_EUR)
        return _ev(
            self.code,
            RuleVerdict.PASS if ok else RuleVerdict.FAIL,
            f"Total {total.value} vs base + IVA = {expected}",
            {"total": float(total.value), "esperado": expected},
            {"total": f"{total.extractor}@{total.confidence:.2f}"},
        )


class DateValidNotFuture:
    code = "DATE_VALID_NOT_FUTURE"

    def evaluate(self, ctx: RuleContext) -> RuleEvaluation:
        cand, why = ctx.pick("fecha", ctx.threshold(self.code, "min_confidence", 0.6))
        if cand is None:
            return _ev(self.code, RuleVerdict.UNKNOWN, f"fecha no fiable: {why}", {})
        parsed = _parse_date(str(cand.value))
        if parsed is None:
            return _ev(self.code, RuleVerdict.UNKNOWN, f"fecha no parseable: {cand.value}", {})
        if parsed > date.today():
            return _ev(self.code, RuleVerdict.FAIL, f"Fecha {parsed} es futura", {"fecha": parsed.isoformat()})
        return _ev(
            self.code, RuleVerdict.PASS, f"Fecha {parsed} válida y no futura",
            {"fecha": parsed.isoformat()}, {"fecha": f"{cand.extractor}@{cand.confidence:.2f}"},
        )


def _parse_date(raw: str) -> date | None:
    for sep in ("/", "-", "."):
        parts = raw.split(sep)
        if len(parts) == 3:
            try:
                d, m, y = (int(p) for p in parts)
                if y < 100:
                    y += 2000
                return date(y, m, d)
            except ValueError:
                continue
    return None


RULE_CODES = (
    "DATE_VALID_NOT_FUTURE", "IBAN_MATCHES_MASTER", "IVA_CONSISTENT", "NIF_IN_MASTER",
    "NO_DOUBLE_PAYMENT", "ORDER_BELONGS_TO_SUPPLIER", "ORDER_PENDING", "TOTALS_MUST_MATCH",
)

_RULE_IMPLS = {r.code: r for r in (
    NifInMaster(), IbanMatchesMaster(), OrderBelongsToSupplier(), OrderPending(),
    NoDoublePayment(), IvaConsistent(), TotalsMustMatch(), DateValidNotFuture(),
)}


def all_rules() -> tuple:
    return tuple(_RULE_IMPLS[c] for c in RULE_CODES)
