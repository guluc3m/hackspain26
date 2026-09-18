// Generado por albertitos.metrics — NO editar a mano.
// Números medidos desde el ledger; cada valor lleva su etiqueta.
#let latenciasPorRung = (:)
#let archivosPorSegundo = ("—", "sin datos")
#let limiteThroughput = ("—", "sin datos")
#let rungMasLento = ("—", "medido")
#let formulaCoste = (
  "electricidad_cpu": ("0.0000 EUR", "estimado"),
  "llamadas_cloud": ("0.0000 EUR", "medido×precio estimado"),
  "tokens_agentes": ("sin datos", "sin datos"),
)
#let costePorArchivo = ("sin datos", "sin datos")
#let costePorLote = ("0.0000 EUR por lote de 500", "sin datos")
#let hardware = ("8 núcleos", "medido")
#let hardwareRam = ("12.0 GB", "medido")
// — T10: dry-run del corpus (.sdd/metrics/corpus-dryrun.json)
#let dryrunTextoUsable = ("471 / 500 (94.2 %)", "medido")
#let dryrunRutas = (
  "rung1 texto usable": "471",
  "raster sin QR": "29",
  "solo QR": "0",
  "errores / timeouts": "0 / 0",
)
#let dryrunLatenciaRung1 = ("0.4 ms", "2.0 ms")
#let dryrunLatenciaRung2 = ("42.1 ms", "73.0 ms")
#let dryrunThroughput = ("2636.364", "medido")
#let dryrunWall = ("3.57 s para 500 archivos", "medido")
// — T10: calibración rung 3 (.sdd/metrics/calibracion/calibracion-rung3.json)
#let calibracionCoberturaTexto = ("texto: media 0.954, p5 0.8 (n=493)", "medido")
#let calibracionCoberturaOcr = ("OCR: media 0.483, p50 0.4 (n=29)", "medido")
#let calibracionDecision = ("word_conf 40.0: 89.7 % OCR pasa (cobertura 0.4: 72.4 % OCR, 100.0 % texto)", "calibrado con corpus (T10)")
// — T12: drills de resiliencia (.sdd/metrics/drills.json)
#let drillsResumen = ("4 pass / 0 fail", "medido (drills automatizados, sin red real)")
#let drillsPorNombre = (
  "rung5-provider-caido": "PASS",
  "backoff-429": "PASS",
  "crash-reanudacion": "PASS",
  "ledger-corrupto": "PASS",
)
// — T13/T14: pendientes de corrida
#let impactoReprocesado = ("PENDIENTE-MEDICIÓN(T14)", "sin datos")
#let resultadosLote1 = ("PENDIENTE-MEDICIÓN(T14)", "sin datos")
#let exactitudLote1 = ("PENDIENTE-MEDICIÓN(T14)", "sin datos")
