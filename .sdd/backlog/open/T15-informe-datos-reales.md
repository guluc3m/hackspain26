# T15 · Informe con datos reales: PDF + ADRs completos
assignee: W3
priority: p1

## Objetivo
Actualizar `albertitos_plan.pdf` (plantilla Typst) con TODA la evidencia medida
que ya existe, dejando placeholders explícitos SOLO donde falte la corrida de
T14 (que va en paralelo).

## Datos disponibles (todos en .sdd/metrics/, LEERLOS y citarlos)
- `corpus-dryrun.json` + `calibracion/calibracion-rung3.json` (T10): 471/500
  texto usable (94,2%), 29 a raster, latencias por rung, throughput medido,
  umbrales calibrados con justificación.
- `drills.json` (T12): resultados de los ensayos de resiliencia.
- `impacto.json` (T13, si ya está) — reprocesado.
- Los ADRs que ya escribiste en T11 se ACTUALIZAN: D-001 con la calibración
  T10 como evidencia (471/29/0-QR); D-05 (revisión humana) con los números de
  la cola de revisión cuando T14 la genere.
- Sección escalabilidad: fórmula de coste explícita con los números reales
  (llamadas cloud × precio; CPU local gratis salvo electricidad — estímalo y
  etiquétalo estimado).

## Reglas duras
- Cero números hardcodeados que no estén en el store/metrics con fuente citada.
- Todo placeholder restante etiquetado `PENDIENTE-MEDICIÓN(T14)`.
- El PDF compilado NO se commitea (docs/report/.gitignore).

## Criterios de aceptación
- PDF re-compilado; ADRs citan archivos de evidencia concretos.
- Test: el flujo datos→.typ sigue verde con los nuevos orígenes.
- `uv run pytest` y `uv run ruff check .` en verde; ticket a closed en el mismo commit.
