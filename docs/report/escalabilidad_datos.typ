// Generado por filemaid.metrics — NO editar a mano.
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
// — T18: impacto del fix (.sdd/metrics/impacto-fix-colapso.json)
#let impactoFix = ("108 reprocesados · 86 NO_PAGAR→PAGAR · 0 regresiones · validación OK", "medido")
// — T23: perfil de carga (.sdd/metrics/perfil-carga.json)
#let perfilCarga = ("UI+2 runners simultáneos: peor p95 7.7 ms, [108.7, 110.0] files/s por runner, 0 ROJOS", "medido")
// — T34: Modo Alberto + app escritorio (ADR-07)
#let modoAlberto = ("iniciar.sh de un paso (idempotente) + UI en lenguaje llano con ayuda contextual + app de escritorio con pywebview (ADR-07)", "medido (implementación con tests)")
#let resultadosLote1 = ("433 PAGAR / 22 NO_PAGAR / 45 ESCALAR (500 archivos)", "medido")
#let exactitudLote1 = ("86.6 % PAGAR automático", "medido")
// — distribución FINAL post-fix (lote1.json, corrida+reprocesado)
#let distribucionFinal = ("433 PAGAR / 22 NO_PAGAR / 45 ESCALAR", "medido")
