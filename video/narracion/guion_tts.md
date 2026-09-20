# Guion TTS — fuente de verdad compartida (voz narrada)

Voz: piper es_ES (carlfm o mls_10246). Objetivo: cada MP4 de escena dura
`frames/30` s; la narración debe caber con ≥0,8 s de holgura. Si sobra,
subir velocidad (piper `--length-scale` menor). Archivos de salida:
`video/narracion/esc1.mp3` … `esc8.mp3` (16 kHz o superior, mono).

| # | Escena | Dur. máx | Palabras |
|---|--------|----------|----------|
| 1 | Portada | 11,2 s | ~27 |
| 2 | Problema | 22,2 s | ~55 |
| 3 | Producto | 19,2 s | ~50 |
| 4 | Escalera | 29,2 s | ~70 |
| 5 | Trazabilidad | 34,2 s | ~78 |
| 6 | ADRs | 19,2 s | ~50 |
| 7 | Resiliencia | 19,2 s | ~47 |
| 8 | Escala | 19,2 s | ~50 |

## Textos definitivos

**esc1 (Portada):**
Alberto paga facturas: quinientas al mes, en PDF. Esto es filemaid, un
asistente que las lee, las comprueba y decide qué pagar — enseñando
siempre la prueba.

**esc2 (Problema):**
Decidir si una factura se paga parece fácil. No lo es. Los grandes modelos
de lenguaje tardan demasiado y a veces inventan; el OCR clásico se
tropieza con cualquier escaneo; y sin evidencia, nadie responde por la
decisión. Ante la duda, la norma es clara: escalar antes que pagar.
Alberto necesita precisión, rapidez y prueba.

**esc3 (Producto):**
La solución vive en una app de escritorio. Suelta los PDFs en una carpeta
y el watcher los ingesta solo. El lote corre veinticuatro entre siete, sin
prompts. Y si algo huele raro, una notificación avisa: solo entonces un
humano mira los candidatos lado a lado y corrige con procedencia.

**esc4 (Escalera):**
¿Cómo lee cada página? Con una escalera de siete escalones. Primero,
texto vectorial: gratis, instantáneo, y resuelve el noventa y cuatro por
ciento del corpus. Si falla: código QR. Luego, OCR local. Después, un
modelo de visión en tu propia máquina. Y solo al final, la nube — último
recurso, nunca respuesta. Cada escalón degrada con calma: el lote nunca
se para.

**esc5 (Trazabilidad):**
¿Por qué no se paga esta factura? Sigamos decisiones reales. Esta es un
duplicado: la regla de doble pago falla, y no se paga. Este escaneo es
ilegible: siete reglas sin respuesta — duda razonable, se escala. Y aquí
la fecha no se lee: se escala también. Cada decisión guarda su evidencia:
huella del archivo, extractor, confianza, configuración y latencia. Nada
se inventa; todo se puede auditar.

**esc6 (ADRs / reglas deterministas):**
Una IA que decide distinto cada vez no es pagable. Por eso el motor es
puro: mismos datos y misma configuración dan la misma salida, byte a
byte. Y cuando encontramos un fallo —ochenta y seis falsos no pagar
corregidos, cero regresiones— queda escrito como decisión de arquitectura:
ocho ADRs.

**esc7 (Resiliencia):**
¿Y si un proveedor cae a mitad del lote? Se degrada: el escalón se salta,
la factura entra en revisión, y el lote sigue. ¿Un crash? Se reanuda sin
duplicados, gracias a la idempotencia por huella. Cuatro simulacros de
desastre: cuatro pasan. Caerse no es opción: degradar.

**esc8 (Escala y coste):**
¿Y el coste? La fórmula es simple: el noventa y cuatro por ciento cuesta
cero; el resto lo paga tu CPU, no tu tarjeta. Quinientas facturas en dos
minutos, cero euros en la nube. Para más volumen, concurrencia. Para
nuevos formatos, un extractor y nada más. Alberto duerme. Y paga lo justo.
