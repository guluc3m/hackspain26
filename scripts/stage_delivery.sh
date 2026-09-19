#!/usr/bin/env bash
# Staging del repo de entrega — T12 + T19 (AGENTS.md §1).
#
# Crea un repo git limpio con EXACTAMENTE los entregables que existan:
#   outcomes.jsonl, outcomes_lote2.jsonl (opcional), albertitos_plan.pdf
# ANTES valida cada JSONL con `python -m albertitos.validate` contra el
# lote de facturas correspondiente y rechaza (exit 1) si falta cualquier
# PDF, hay duplicados, result inválido o se detecta un secreto
# (apiKey|sk-|FACTURAS2009) en lo que va a copiar.
#
# T19: outcomes_lote2.jsonl es OPCIONAL mientras no llegue el lote 2 —
# si falta, se avisa y se hace staging con los que existan. outcomes.jsonl
# y albertitos_plan.pdf son OBLIGATORIOS (falla limpio si faltan).
#
# Idempotente: re-ejecutar es seguro (sobreescribe y commita solo si cambió).
#
# Variables (todas con default razonable):
#   OUTCOMES_LOTE1  (outcomes.jsonl)          OUTCOMES_LOTE2 (outcomes_lote2.jsonl)
#   PLAN_PDF        (albertitos_plan.pdf)     DESTINO        (~/delivery-repo)
#   FACTURAS_LOTE1  (caja-de-alberto/facturas) FACTURAS_LOTE2 (= FACTURAS_LOTE1)
#   PYTHON          (uv run python)

set -euo pipefail

OUTCOMES_LOTE1="${OUTCOMES_LOTE1:-outcomes.jsonl}"
OUTCOMES_LOTE2="${OUTCOMES_LOTE2:-outcomes_lote2.jsonl}"
PLAN_PDF="${PLAN_PDF:-albertitos_plan.pdf}"
FACTURAS_LOTE1="${FACTURAS_LOTE1:-caja-de-alberto/facturas}"
FACTURAS_LOTE2="${FACTURAS_LOTE2:-$FACTURAS_LOTE1}"
DESTINO="${DESTINO:-$HOME/delivery-repo}"
PYTHON="${PYTHON:-uv run python}"

err() {
	echo "ERROR: $*" >&2
	exit 1
}

# ---------------------------------------------------------------- 0 · entradas
[ -f "$OUTCOMES_LOTE1" ] || err "falta el artefacto '$OUTCOMES_LOTE1': genera outcomes.jsonl antes de hacer staging (no se ha copiado nada)"
[ -f "$PLAN_PDF" ] || err "falta el artefacto '$PLAN_PDF': compila albertitos_plan.pdf antes de hacer staging (no se ha copiado nada)"
[ -d "$FACTURAS_LOTE1" ] || err "no existe el directorio de facturas del lote 1: $FACTURAS_LOTE1"

TIENE_LOTE2=1
if [ ! -f "$OUTCOMES_LOTE2" ]; then
	echo "AVISO: $OUTCOMES_LOTE2 aún no existe (lote 2 pendiente) — staging con los entregables disponibles."
	TIENE_LOTE2=0
else
	[ -d "$FACTURAS_LOTE2" ] || err "no existe el directorio de facturas del lote 2: $FACTURAS_LOTE2"
fi

ABS_LOTE1=$(readlink -f "$OUTCOMES_LOTE1")
ABS_PDF=$(readlink -f "$PLAN_PDF")

# ------------------------------------------------------- 1 · higiene de secretos
if grep -Eqn "apiKey|sk-[A-Za-z0-9]|FACTURAS2009" "$ABS_LOTE1" 2>/dev/null; then
	err "posible secreto en $OUTCOMES_LOTE1 (apiKey|sk-|FACTURAS2009) — revisa; NADA se ha copiado"
fi
if [ "$TIENE_LOTE2" = 1 ]; then
	ABS_LOTE2=$(readlink -f "$OUTCOMES_LOTE2")
	if grep -Eqn "apiKey|sk-[A-Za-z0-9]|FACTURAS2009" "$ABS_LOTE2" 2>/dev/null; then
		err "posible secreto en $OUTCOMES_LOTE2 (apiKey|sk-|FACTURAS2009) — revisa; NADA se ha copiado"
	fi
fi

# ------------------------------------------------ 2 · validación de contrato
echo "Validando lote 1 ($OUTCOMES_LOTE1) contra $FACTURAS_LOTE1 …"
$PYTHON -m albertitos.validate --outcomes "$ABS_LOTE1" --facturas "$FACTURAS_LOTE1" \
	|| err "$OUTCOMES_LOTE1 no pasa el validador de contrato (líneas/faltantes/duplicados/result)"

if [ "$TIENE_LOTE2" = 1 ]; then
	echo "Validando lote 2 ($OUTCOMES_LOTE2) contra $FACTURAS_LOTE2 …"
	$PYTHON -m albertitos.validate --outcomes "$ABS_LOTE2" --facturas "$FACTURAS_LOTE2" \
		|| err "$OUTCOMES_LOTE2 no pasa el validador de contrato"
fi

# ------------------------------------------------------- 3 · staging idempotente
mkdir -p "$DESTINO"
cd "$DESTINO"
[ -d .git ] || git init -q
# la raíz queda EXACTAMENTE con los entregables: se retira cualquier resto anterior
find . -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
cp "$ABS_LOTE1" outcomes.jsonl
cp "$ABS_PDF" albertitos_plan.pdf
[ "$TIENE_LOTE2" = 1 ] && cp "$ABS_LOTE2" outcomes_lote2.jsonl

git add -A
if ! git diff --cached --quiet; then
	git -c user.name="staging" -c user.email="staging@albertitos.local" -c commit.gpgsign=false \
		commit -q -m "Entrega: outcomes y albertitos_plan.pdf"
fi

# ------------------------------------------------------------- 4 · comprobación final
N=$(ls -A | grep -vc '^\.git$' || true)
ESPERADOS=$((2 + TIENE_LOTE2))
[ "$N" -eq "$ESPERADOS" ] || err "la raíz de $DESTINO debe contener exactamente $ESPERADOS entregables; hay $N"

if [ "$TIENE_LOTE2" = 1 ]; then
	echo "OK: $DESTINO listo con exactamente 3 entregables (outcomes.jsonl, outcomes_lote2.jsonl, albertitos_plan.pdf)."
else
	echo "OK: $DESTINO listo con 2 entregables (outcomes.jsonl, albertitos_plan.pdf). Falta outcomes_lote2.jsonl: cuando exista, re-ejecuta este script."
fi