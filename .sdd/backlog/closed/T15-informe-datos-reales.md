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

## Cerrado — decisiones tomadas (W3)

- **Nuevos orígenes medidos en el flujo store→datos** (`albertitos.metrics`):
  `metricas_t10_t12()` lee `.sdd/metrics/corpus-dryrun.json`,
  `calibracion/calibracion-rung3.json`, `drills.json` e `impacto.json` (si
  existe) y emite bindings #let nuevos en `escalabilidad_datos.typ`
  (dryrunTextoUsable, dryrunRutas, latencias rung 1/2, throughput rung 1,
  calibración de umbrales, drillsPorNombre, impactoReprocesado,
  resultadosLote1, exactitudLote1). Cero números hardcodeados: todo sale de
  los JSON con fuente citada; lo ausente ⇒ «sin datos» /
  «PENDIENTE-MEDICIÓN(T14)».
- **escalabilidad.typ**: secciones nuevas con fuente citada — Dry-run del
  corpus real (471/500 = 94,2 % texto, 29 raster, 0 QR; latencias y
  throughput rung 1 medidos), Calibración rung 3 (distribuciones + decisión
  extract-v2: word_conf 40, cobertura 0.4), Drills de resiliencia (4/4
  PASS), Lote 1/reprocesado con placeholders T14.
- **Fórmula de coste**: CPU local gratis salvo electricidad — kWh =
  horas × potencia (0.1 kW estimada) × €/kWh (0.25 estimado), término
  «electricidad_cpu» etiquetado ESTIMADO; llamadas cloud nº × precio
  (medidas en T14, el dry-run no factura).
- **ADRs actualizados con evidencia citada**: ADR 02 (extracción) lleva la
  calibración T10 (471/29/0-QR, umbrales extract-v2); ADR 03 lleva el drill
  crash-reanudacion; ADR 05 lleva drills rung5/backoff + cola de revisión
  PENDIENTE-MEDICIÓN(T14). PDF compilado (13 páginas) y NO commitado.
- **Tests**: nuevos orígenes fluyen al .typ con fixtures T10/T12 sembrados;
  la plantilla cita los ficheros de evidencia; placeholders solo vía
  bindings. 155 passed, ruff limpio, sin secretos.
