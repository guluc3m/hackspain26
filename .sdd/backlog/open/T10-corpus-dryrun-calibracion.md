# T10 · Dry-run de la escalera sobre el corpus real + calibración
assignee: W1
priority: p1

## Objetivo
Ejecutar tu escalera (T1) sobre los **500 PDFs reales** de
`caja-de-alberto/facturas/` (SOLO lectura) con rungs 1–2 (texto + raster/QR,
sin VLM aún) y producir la evidencia medida que la arquitectura promete.

## Entregables
- Corrida idempotente (`--limit`/`--only` de T8 si ya existe; si no, un script
  en `src/albertitos/` con la misma disciplina de cache/ledger).
- `.sdd/metrics/corpus-dryrun.json`: distribución medida — nº de archivos con
  capa de texto usable, nº que caen a raster/QR, nº solo-QR, latencias medias
  y p95 por rung, fallos con causa (y lista de archivos problemáticos).
- Umbrales: usando esa distribución, propon calibrados los dos umbrales de
  "confianza suficiente" del rung 3 (confianza de palabras + cobertura de
  campos) con los valores y la JUSTIFICACIÓN escrita en
  `.sdd/metrics/calibracion.md` — es la evidencia del ADR D-001 (AGENTS.md §13).
  Nada de números mágicos: cada umbral citando qué porcentaje del corpus queda
  por encima/debajo.

## Reglas duras
- Nunca modificar `caja-de-alberto/`. Timeout por archivo ⇒ registrar y seguir.
- El dry-run NO decide resultados: solo mide extracción. Los resultados vendrán
  del runner T8 con el motor completo.
- Concurrencia ≤ 2 archivos en vuelo; medir files/s real del rung 1.

## Criterios de aceptación
- Test: la corrida sobre un subconjunto de fixtures es reproducible (re-run
  idéntico, 0 re-procesos) y las métricas se generan.
- `.sdd/metrics/corpus-dryrun.json` existe con las 500 entradas (o su resumen)
  tras la corrida real, y la suma de rutas de la escalera cuadra con el total.
- `uv run pytest` y `uv run ruff check .` en verde; ticket a closed en el mismo commit.
