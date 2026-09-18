# T10 · Dry-run de la escalera sobre el corpus real + calibración
assignee: W1
priority: p1

## Objetivo
Ejecutar tu escalera (T1) sobre los **500 PDFs reales** de
`caja-de-alberto/facturas/` (SOLO lectura) con rungs 1–2 (texto + raster/QR,
sin VLM aún) y producir la evidencia medida que la arquitectura promete.

## Entregables
- Corrida idempotente (misma disciplina de cache/ledger que T1; `--limit`/`--only`
  para pruebas parciales).
- `.sdd/metrics/corpus-dryrun.json`: distribución medida — nº de archivos con
  capa de texto usable, nº que caen a raster/QR, nº solo-QR, latencias medias
  y p95 por rung, fallos con causa (y lista de archivos problemáticos).
- Umbrales del rung 3 (confianza de palabras + cobertura de campos) calibrados
  con esa distribución y justificación escrita en `.sdd/metrics/calibracion.md`
  — es la evidencia del ADR D-001 (AGENTS.md §13). Nada de números mágicos:
  cada umbral citando qué porcentaje del corpus queda por encima/debajo.

## Reglas duras
- Nunca modificar `caja-de-alberto/`. Timeout por archivo ⇒ registrar y seguir.
- El dry-run NO decide resultados: solo mide extracción.
- Concurrencia ≤ 2 archivos en vuelo; medir files/s real del rung 1.

## Criterios de aceptación
- Test: la corrida sobre un subconjunto de fixtures es reproducible (re-run
  idéntico, 0 re-procesos) y las métricas se generan.
- `.sdd/metrics/corpus-dryrun.json` cubre los 500 archivos y la suma de rutas
  de la escalera cuadra con el total.
- `uv run pytest` y `uv run ruff check .` en verde; ticket a closed en el mismo commit.
