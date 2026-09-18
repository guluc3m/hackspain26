#!/usr/bin/env bash
# Staging del repo de entrega — T12 (AGENTS.md §1).
#
# Crea un repo git limpio con EXACTAMENTE 3 archivos en la raíz:
#   outcomes.jsonl, outcomes_lote2.jsonl, albertitos_plan.pdf
# ANTES valida ambos JSONL con `python -m albertitos.validate` contra el
# lote de facturas correspondiente y rechaza (exit 1) si falta cualquier
# PDF (500+40), hay duplicados, result inválido o se detecta un secreto
# (apiKey|sk-|FACTURAS2009) en lo que va a copiar.
#
# Idempotente: re-ejecutar es seguro (sobreescribe y commita solo si cambió).
# Si outcomes.jsonl aún no existe, falla limpio con mensaje claro.
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
for f in "$OUTCOMES_LOTE1" "$OUTCOMES_LOTE2" "$PLAN_PDF"; do
	[ -f "$f" ] || err "falta el artefacto '$f': genera los entregables antes de hacer staging (no se ha copiado nada)"
done
[ -d "$FACTURAS_LOTE1" ] || err "no existe el directorio de facturas del lote 1: $FACTURAS_LOTE1"
[ -d "$FACTURAS_LOTE2" ] || err "no existe el directorio de facturas del lote 2: $FACTURAS_LOTE2"

ABS_LOTE1=$(readlink -f "$OUTCOMES_LOTE1")
ABS_LOTE2=$(readlink -f "$OUTCOMES_LOTE2")
ABS_PDF=$(readlink -f "$PLAN_PDF")

# ------------------------------------------------------- 1 · higiene de secretos
if grep -Eqn "apiKey|sk-[A-Za-z0-9]|FACTURAS2009" "$ABS_LOTE1" "$ABS_LOTE2" 2>/dev/null; then
	err "posible secreto en los JSONL (apiKey|sk-|FACTURAS2009) — revisa; NADA se ha copiado"
fi

# ------------------------------------------------ 2 · validación de contrato
echo "Validando lote 1 ($OUTCOMES_LOTE1) contra $FACTURAS_LOTE1 …"
$PYTHON -m albertitos.validate --outcomes "$ABS_LOTE1" --facturas "$FACTURAS_LOTE1" \
	|| err "outcomes.jsonl no pasa el validador de contrato (líneas/faltantes/duplicados/result)"

echo "Validando lote 2 ($OUTCOMES_LOTE2) contra $FACTURAS_LOTE2 …"
$PYTHON -m albertitos.validate --outcomes "$ABS_LOTE2" --facturas "$FACTURAS_LOTE2" \
	|| err "outcomes_lote2.jsonl no pasa el validador de contrato"

# ------------------------------------------------------- 3 · staging idempotente
mkdir -p "$DESTINO"
cd "$DESTINO"
[ -d .git ] || git init -q
# la raíz queda EXACTAMENTE con los 3 entregables: se retira cualquier resto anterior
find . -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
cp "$ABS_LOTE1" outcomes.jsonl
cp "$ABS_LOTE2" outcomes_lote2.jsonl
cp "$ABS_PDF" albertitos_plan.pdf

git add -A
if ! git diff --cached --quiet; then
	git -c user.name="staging" -c user.email="staging@albertitos.local" -c commit.gpgsign=false \
		commit -q -m "Entrega: outcomes (lote 1 + lote 2) y albertitos_plan.pdf"
fi

# ------------------------------------------------------------- 4 · comprobación final
N=$(ls -A | grep -vc '^\.git$' || true)
[ "$N" -eq 3 ] || err "la raíz de $DESTINO debe contener exactamente 3 archivos; hay $N"

echo "OK: $DESTINO listo con exactamente 3 entregables (outcomes.jsonl, outcomes_lote2.jsonl, albertitos_plan.pdf)."
