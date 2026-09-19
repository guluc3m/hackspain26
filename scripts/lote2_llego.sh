#!/usr/bin/env bash
# T38-ID1 · «Llegó el lote 2»: ingesta + emisión + validación + staging en
# UN comando, para que el sábado a las 16:00 UTC sea un solo paso sin error
# humano de orden (el flujo exacto de T21, atado y verificado).
#
#   bash scripts/lote2_llego.sh <dir-lote2>
#
# 1. Chequeo previo (FALLA LIMPIO sin tocar nada):
#    - el directorio existe y tiene EXACTAMENTE ESPERADOS_LOTE2 PDFs (40),
#    - NINGÚN basename solapa con el lote 1 (sobreposición = error de
#      ingesta: file_id es el basename EXACTO y dos lotes con el mismo
#      nombre corrompen la identidad de la factura),
#    - regla v4 y maestro existen (el lote 2 corre con reglas COMO DATOS).
# 2. Ingesta: runner con regla v4 + run_id lote2 + emit-scope lote
#    (el lote 1 y outcomes.jsonl NO se tocan jamás).
# 3. El runner acaba con el validador de contrato contra el dir del lote 2;
#    si falla, exit 1 (el store conserva el histórico; re-run es idempotente).
# 4. Staging: scripts/stage_delivery.sh (2→3 entregables).
#
# Variables (defaults razonables, alineadas con stage_delivery.sh):
#   ESPERADOS_LOTE2 (40)        FACTURAS_LOTE1 (caja-de-alberto/facturas)
#   RULES_LOTE2 (src/albertitos/rules/regla_v4.yaml)
#   MAESTRO (caja-de-alberto/FINAL_v7_DEFINITIVO_ahorasi.xlsx)
#   OUTCOMES_LOTE2 (outcomes_lote2.jsonl)   STORE_ROOT_LOTE2 (.sdd)
#   OUTCOMES_LOTE1 / PLAN_PDF / DESTINO — pasan a stage_delivery.sh
#   PYTHON (uv run python)
set -euo pipefail

err() {
	echo "ERROR: $*" >&2
	exit 1
}

cd "$(dirname "$0")/.."
. "$(dirname "$0")/_ensure_uv.sh"
PYTHON="${PYTHON:-uv run python}"
DIR_LOTE2="${1:-}"
ESPERADOS="${ESPERADOS_LOTE2:-40}"
FACTURAS_LOTE1="${FACTURAS_LOTE1:-caja-de-alberto/facturas}"
RULES_LOTE2="${RULES_LOTE2:-src/albertitos/rules/regla_v4.yaml}"
MAESTRO="${MAESTRO:-caja-de-alberto/FINAL_v7_DEFINITIVO_ahorasi.xlsx}"
OUTCOMES_LOTE2="${OUTCOMES_LOTE2:-outcomes_lote2.jsonl}"
STORE_ROOT="${STORE_ROOT_LOTE2:-.sdd}"

# ------------------------------------------------------- 0 · chequeo previo
[ -n "$DIR_LOTE2" ] || err "uso: bash scripts/lote2_llego.sh <dir-lote2>"
[ -d "$DIR_LOTE2" ] || err "no existe el directorio del lote 2: $DIR_LOTE2 (nada se ha tocado)"
[ -d "$FACTURAS_LOTE1" ] || err "no existe el directorio del lote 1: $FACTURAS_LOTE1 (no se puede comprobar la sobreposición)"
[ -f "$RULES_LOTE2" ] || err "no existe $RULES_LOTE2 (regla v4 como DATOS) — el lote 2 no debe correr con v3"
[ -f "$MAESTRO" ] || err "no existe el maestro: $MAESTRO"

N_PDFS=$(find "$DIR_LOTE2" -maxdepth 1 -type f -name '*.pdf' | wc -l)
[ "$N_PDFS" -eq "$ESPERADOS" ] \
	|| err "el lote 2 tiene $N_PDFS PDFs, se esperaban $ESPERADOS (ESPERADOS_LOTE2) — la ingesta se detiene sin tocar nada"

SOLAPADOS=$(comm -12 \
	<(find "$DIR_LOTE2" -maxdepth 1 -type f -name '*.pdf' -printf '%f\n' | sort) \
	<(find "$FACTURAS_LOTE1" -maxdepth 1 -type f -name '*.pdf' -printf '%f\n' | sort))
[ -z "$SOLAPADOS" ] || err "sobreposición de file_id con el lote 1 (error de ingesta): $(echo "$SOLAPADOS" | tr '\n' ' ')"

echo "OK: lote 2 con $N_PDFS PDFs, sin solaparse con el lote 1, regla v4 presente."

# ------------------------------------------------------- 1 · ingesta (T21)
echo "Ingesta del lote 2 (run_id=lote2, emit-scope=lote, regla v4 como DATOS)…"
$PYTHON -m albertitos.run \
	--facturas "$DIR_LOTE2" \
	--outcomes "$OUTCOMES_LOTE2" \
	--store-root "$STORE_ROOT" \
	--rules "$RULES_LOTE2" \
	--maestro "$MAESTRO" \
	--run-id lote2 \
	--emit-scope lote

# El runner ya validó el contrato al terminar; si llegó aquí, salió en verde.
echo "Validador de contrato del lote 2: OK (integrado en el runner)."

# ------------------------------------------------------- 2 · staging
echo "Staging del repo de entrega (ahora con lote 2: 2→3 entregables)…"
FACTURAS_LOTE2="$DIR_LOTE2" bash scripts/stage_delivery.sh

# ------------------------------------------------------- 3 · resumen en español
N_LINEAS=$(grep -c . "$OUTCOMES_LOTE2" 2>/dev/null || true)
PAGAR=$(grep -c '"result": "PAGAR"' "$OUTCOMES_LOTE2" 2>/dev/null || true)
NO_PAGAR=$(grep -c '"result": "NO_PAGAR"' "$OUTCOMES_LOTE2" 2>/dev/null || true)
ESCALAR=$(grep -c '"result": "ESCALAR"' "$OUTCOMES_LOTE2" 2>/dev/null || true)
echo "—— Lote 2 listo ——"
echo "Ingestados: $N_LINEAS facturas · PAGAR $PAGAR · NO_PAGAR $NO_PAGAR · ESCALAR $ESCALAR"
echo "outcomes.jsonl del lote 1 intacto · validación OK · staging listo en \${DESTINO:-~/delivery-repo}"