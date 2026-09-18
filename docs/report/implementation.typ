= Implementación

La implementación es una pipeline en Python (`src/albertitos/`) organizada en
los bloques de la arquitectura, con cada fase escribiendo evidencia trazable:

#table(
  columns: (auto, auto, auto),
  table.header([Fase], [Módulo], [Salida]),
  [Extracción], [`albertitos.extract`], [_Features_ crudas por página, cada una con extractor, versión, latencia y hash],
  [Parser], [`albertitos.parser`], [Campos con TODAS las lecturas candidatas (extractor, valor, confianza en $[0,1]$)],
  [Decisión], [`albertitos.rules` + `albertitos.engine`], [Resultado + códigos de regla + _snapshot_ de configuración],
  [Store], [`albertitos.store` + `albertitos.emit`], [SQLite + _ledger_ JSONL _append-only_ bajo `.sdd/`; emisión de `outcomes.jsonl`],
  [UI], [`albertitos.ui`], [Operaciones, Facturas, Revisión, Reglas y Salud (FastAPI + Jinja2 + HTMX, lectura en solo lectura)],
)

== Escalera de extracción (por página)

Cada página recorre los peldaños en orden coste/calidad, y cualquier peldaño
puede faltar sin detener el lote: se registra `skipped:<motivo>` y se continúa.

+ *Capa de texto* (`pypdf`): aceptada solo si pasa un control de plausibilidad
de glifos — las fuentes CID rotas producen _mojibake_ con confianza aparente.
+ *Render + QR* (`pypdfium2` + `zxing-cpp`): si la página solo contiene QRs,
el _payload_ decodificado ES el contenido de la página.
+ *OCR local* (`tesseract`): confianza = media de palabras ponderada por
longitud + término de cobertura de campos esperados.
+ *VLM local*: PaddleOCR-VL-1.6 q8_0 vía `llama-server` (decisión de modelo
registrada en `docs/decisiones/DECISIONS.md`, D-001/D-002), temperatura 0,
misma puerta de confianza de dos partes.
+ *VLM nube* (rung 5): `deepseek-v4.1-flash`, SOLO para páginas que fallen
tesseract + VLM local; su lectura es OTRO candidato con confianza, jamás
respuesta automática. Los modelos Qwen3.8-27B y qwen-next-flash están VETADOS
en todos los roles (servidor de IA local del usuario caído; AGENTS §13).

== Estado, idempotencia y reanudación

La clave de caché es `(sha256, stage, engine_version, config_version)`:
reprocesar un ítem completado es un no-op que reutiliza la evidencia
almacenada, y un _crash_ a mitad de lote pierde como mucho el ítem en vuelo.
El estado vive en disco (SQLite + _ledger_ append-only), nunca solo en memoria
ni en `/tmp`, de modo que la ejecución es reanudable desde cualquier punto y
el histórico alimenta la retroalimentación (§Retroalimentación).

== UI de operaciones

Cinco pantallas en español llano (AGENTS §9): Operaciones (estado del lote,
cola, coste, versión de reglas), Facturas (resultado, reglas que deciden,
cadena de evidencia, extractor, latencia, confianza, página fuente), Revisión
(cola de ESCALAR con imagen de página junto a cada lectura candidata y
desacuerdo resaltado), Reglas (set activo, umbrales y «¿qué pasaría si...?») y
Salud (fallos de proveedor, reintentos, estado degradado). La UI lee el _store_
en SOLO LECTURA y jamás decide: las correcciones humanas se encolan como
_overrides_ con _provenance_ y el motor determinista recalcula.

== Estado de la implementación

- Integrado y probado: escalera de extracción por páginas (T1), parser con
  todas las candidatas (T2), motor de reglas + store idempotente + emisión
  de `outcomes.jsonl` con validador de contrato (T3, T4, T9), rung 5 cloud
  con cola de revisión (T7), UI (T5), métricas e informe (T6, T9).
- *PENDIENTE-MEDICIÓN*: el _runner_ de lote end-to-end (T8) y el _dry-run_
  sobre los 500 PDFs con calibración de umbrales (T10) aún no han corrido
  en este nodo; mientras tanto, los números de throughput y coste del lote
  se muestran como ESTIMADO o «sin datos medidos» — nunca como medidos.
