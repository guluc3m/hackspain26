#import "lib.typ": *
#import "diagram/arquitectura-general.typ": arquitectura-general
#import "diagram/escalera-confianza.typ": escalera-confianza

= Arquitectura general del sistema
La arquitectura se sostiene sobre tres principios:
- *Dos fases estrictamente separadas.* La *extracción* produce _features_
  (material bruto, sin interpretación) y el *parser* la interpreta en _campos_:
  candidatos con su extractor y confianza en, que nunca se colapsan en el
  almacén; sólo la regla que necesita un escalar elige uno, dejando constancia
  de cuál y por qué.
- *Decisión determinista y pura.* El motor consume campos + reglas y emite el
  resultado junto a los códigos de regla que lo produjeron y un _snapshot_ de la
  configuración activa. Umbrales y frontera `NO_PAGAR`/`ESCALAR` son
  configuración, no código.
- *Trazabilidad e idempotencia.* Cada fase sella una fila de evidencia se
  cachea: un re-run nunca repite ni re-factura trabajo. El estado vive en la
  base de datos.

El flujo completo, con el almacén y la revisión humana alimentándose de la
evidencia de cada fase:

#figure(arquitectura-general(), caption: [Arquitectura general])


== Bloque de extracción: La Escalera de Confianza Multiescalón

La extracción no es una caja negra: es una *escalera de 7 escalones calibrada
por página*, diseñada para resolver al mínimo coste y escalar con rigor
matemático ante cualquier anomalía documental.

#figure(escalera-confianza(), caption: [Escalera de confianza])
#v(4pt)
#v(6pt)

=== Parser Resiliente Multilingüe

El _parser_ consume las _features_ y extrae candidatos preservando procedencia y
confianza:
- *Inmune a trampas OCR*: Normaliza espacios invisibles (`\u200b`), separadores
  combinados (`1 426,40`, `1,135,20`) y acrónimos fusionados (`IVA21%27150`).
- *Políglota nativo*: Reconoce importes y reglas fiscales en 7 idiomas (español,
  inglés, francés, alemán, italiano, catalán y portugués).
- *Desambiguación emisor/cliente*: Prioriza siempre el NIF del proveedor real
  sobre el CIF del cliente (`Banco Miralmar`), evitando falsos positivos de
  fraude.
- *Valores múltiples*: Todos los candidatos coexisten en `values[]`. La
  resolución escalar se difiere a la regla que la consume, garantizando
  trazabilidad y auditoría forense.
