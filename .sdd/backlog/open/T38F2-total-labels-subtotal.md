# T38-F2 · Labels de total: «Subtotal» genera candidato fantasma y «Total facturado» no se captura
assignee: W2 (parser) — supervisor (puede cambiar resultados)
priority: p1
severidad: p1

## Hallazgo (dos caras del mismo bug, verificado con el parser real)
En `src/albertitos/parse/extractors.py`:
1. `_RE_LABEL_TOTAL = (?:importe\s*total|total\s*a\s*pagar|total\s*factura|total)`
   — la alternativa `total` matchea DENTRO de «Subtotal» ⇒ una línea
   «Subtotal: EUR 1409.40» produce un candidato de `total` (el T17 lo medido:
   candidatos [1409.4, 1705.37]).
2. «Total facturado: EUR 1705.37» NO produce candidato: tras la etiqueta la
   regex solo admite `[:.\-]*` antes del número, y «facturado» corta el match.
   Repro: texto con «Subtotal: EUR 1409.40» + «Total facturado: EUR
   1705.37» ⇒ candidatos de total = [1409.4] SOLAMENTE.

## Consecuencia
Una factura legítima que se redacte «Total facturado» (y no «TOTAL A PAGAR»)
termina con total = Subtotal ⇒ ORDER_AMOUNT_MATCHES:FAIL + TOTALS_MUST_MATCH:FAIL
⇒ NO_PAGAR falso que ADR-06 NO puede salvar (no hay segundo candidato).

## Reproducción (pasos exactos)
Ver ticket T38-F1: mismo esqueleto; con el texto de arriba el campo `total`
solo trae 1409.4 y la decisión es NO_PAGAR (verificado hoy contra
maestro_fixture con pedido importe=1705.37).

## Fix propuesto
- `(?<![A-Za-z])total` (frontera a la izquierda) para NO matchear «Subtotal»;
- `total\s+\w{3,15}\s*[:.\-]*` para «Total facturado/documento/…».
ATENCIÓN: cambiar los candidatos puede cambiar resultados ⇒ supervisor decide
y reprocesar con diff (mecanismo T13/impacto).
