# Guion TTS — fuente de verdad compartida (voz narrada)

Voz: **piper** `es_ES-carlfm-x_low` (16 kHz mono), modelo en
`models/tts/es_ES-carlfm-x_low.onnx`. La narración debe **llenar** su escena:
holgura objetivo 0,8–1,5 s por toma (nunca >2,0 s de aire muerto), y nunca menos
de 0,5 s. El ritmo se ajusta por escena con `--length-scale` (≤1,12) desde
`narracion/gen_tts.py`, que es la única vía de regeneración:

```sh
python3 narracion/gen_tts.py            # regenera esc1..esc8 (autotune de ritmo)
python3 narracion/gen_tts.py --only 5   # solo una escena
python3 narracion/gen_tts.py --dry-run  # mide sin escribir
```

Salida: `video/narracion/esc{N}.wav` y su copia byte-idéntica en
`video/public/narracion/esc{N}.wav` (es la que sirve `staticFile`). Los textos de
abajo son la fuente de verdad narrativa: no se reescriben al regenerar audio.

## Presupuesto por escena

`presupuesto = escena_s − entrada_s`; `toma_máx = presupuesto − 0,8 s` (holgura
objetivo). La holgura dura es ≥0,5 s.

| # | Escena | Escena s | Entrada s | Presupuesto s | Toma máx s | Palabras |
|---|--------|----------|-----------|---------------|------------|----------|
| 1 | Portada     | 12 | 1,0 | 11,0 | 10,2 | 30 |
| 2 | Problema    | 23 | 1,0 | 22,0 | 21,2 | 55 |
| 3 | Producto    | 20 | 1,2 | 18,8 | 18,0 | 58 |
| 4 | Escalera    | 30 | 2,0 | 28,0 | 27,2 | 71 |
| 5 | Trazabilidad| 35 | 2,5 | 32,5 | 31,7 | 85 |
| 6 | ADRs        | 20 | 1,5 | 18,5 | 17,7 | 52 |
| 7 | Resiliencia | 20 | 1,0 | 19,0 | 18,2 | 55 |
| 8 | Escala      | 20 | 1,0 | 19,0 | 18,2 | 52 |

## Qué tiene que quedar claro (cliente / servidor)

- **Cliente = la app de escritorio.** Vigilante de carpeta, escalera de
  extracción, motor de reglas y almacén local: **decide sola**, sin depender de
  la red.
- **Servidor = sincronización de resultados y evidencias, cola de revisión e
  histórico.** **No decide.** Si el servidor no está, el cliente sigue decidiendo
  en local y sincroniza cuando vuelve: nada se bloquea.
- Reparto: lo **introduce** el producto (esc3), el **histórico/evidencia en el
  servidor** cierra la trazabilidad (esc5) y la **independencia offline** se
  afirma en resiliencia (esc7).

## Textos definitivos

**esc1 (Portada):**
Alberto paga facturas: quinientas al mes, en PDF. Esto es filemaid, un
asistente que las lee, las comprueba y decide qué pagar en su máquina —
enseñando siempre la prueba.

**esc2 (Problema):**
Decidir si una factura se paga parece fácil. No lo es. Los grandes modelos
de lenguaje tardan demasiado y a veces inventan; el OCR clásico se
tropieza con cualquier escaneo; y sin evidencia, nadie responde por la
decisión. Ante la duda, la norma es clara: escalar antes que pagar.
Alberto necesita precisión, rapidez y prueba.

**esc3 (Producto):**
El producto es la app de escritorio: el cliente. Vigila la carpeta, extrae
con la escalera, aplica las reglas y decide sola, con su almacén local. El
lote corre veinticuatro entre siete, sin prompts. El servidor no decide:
sincroniza resultados y sirve la cola de revisión. Y si algo huele raro,
avisa y un humano corrige con procedencia.

**esc4 (Escalera):**
¿Cómo lee cada página? Con una escalera de siete escalones que el cliente
recorre solo, de lo barato a lo caro. Primero, texto vectorial: gratis,
instantáneo, y resuelve el noventa y cuatro por ciento del corpus. Si
falla: código QR. Luego, OCR local. Después, un modelo de visión en tu
propia máquina. Y solo al final, la nube — último recurso, nunca
respuesta. Cada escalón degrada con calma: el lote nunca se para.

**esc5 (Trazabilidad):**
¿Por qué no se paga esta factura? Sigamos decisiones reales. Esta es un
duplicado: la regla de doble pago falla, y no se paga. Este escaneo es
ilegible: siete reglas sin respuesta — duda razonable, se escala. Y aquí
la fecha no se lee: se escala también. Cada decisión guarda su evidencia:
huella del archivo, extractor, confianza, configuración y latencia. Esa
evidencia y el histórico viven en el servidor: es el registro común y la
cola de revisión. Nada se inventa; todo se puede auditar, desde cualquier
máquina.

**esc6 (ADRs / reglas deterministas):**
Una IA que decide distinto cada vez no es pagable. Por eso el motor del
cliente es puro: mismos datos y misma configuración dan la misma salida,
byte a byte. Y cuando encontramos un fallo —ochenta y seis falsos no pagar
corregidos, cero regresiones— queda escrito como decisión de arquitectura:
ocho ADRs.

**esc7 (Resiliencia):**
¿Y si un proveedor cae a mitad del lote? El escalón se salta y el lote
sigue. ¿Un crash? Se reanuda sin duplicados, por idempotencia de huella.
¿Y si cae el servidor? Da igual: el cliente decide en local y sincroniza
al volver; nada se bloquea. Cuatro simulacros: cuatro pasan. Caerse no es
opción: degradar.

**esc8 (Escala y coste):**
¿Y el coste? La fórmula es simple: el noventa y cuatro por ciento cuesta
cero; el resto lo paga tu CPU, no tu tarjeta. Quinientas facturas en dos
minutos, cero euros en la nube. Para más volumen, concurrencia. Para
nuevos formatos, un extractor y nada más. Alberto duerme. Y paga lo justo.
