# Guion de defensa — 500 Sombras de Alberto (10 min)

> Regla de oro del guion: **cada cifra tiene su fuente** (ver notas al pie).
> Lo que no esté medido se dice PENDIENTE; nunca se improvisa un número.
>
> Demo en vivo: `ALBERTITOS_STORE=.sdd/lote1/ledger uv run uvicorn albertitos.ui.app:app`
> (ver checklist operativo al final). El store real del lote 1 es SOLO LECTURA.

## 1. Demo y contexto (2 min) — qué le ahorra a Alberto

**Frase de apertura**: «Alberto recibe 500 facturas en PDF y tiene que decidir
cuáles pagar. Nuestro sistema las lee, las decide con reglas deterministas y
le deja las dudosas en una cola de revisión — con la evidencia al lado. Hoy
las 500 están decididas: 433 PAGAR por 2 331 130,43 €, 22 NO_PAGAR y 45 para
revisión (resumen ejecutivo al lado).» [1][14]

**5. Resumen ejecutivo** (`resumen_alberto.pdf` / `.html`, T26): «¿qué pago
hoy y por qué?» — total, top-10 por importe, motivos de NO_PAGAR en llano
y avisos (duplicados, fantasmas). Y el BONUS T30: los escalados priorizados
por DINERO EN RIESGO — «revisando estas N facturas cubres el X % del dinero
en juego» (leer el nº y el % de la pantalla, son regenerables). Todo con
fuente: store × maestro. [1][13]

**En pantalla (ui/app.py, datos reales del lote 1):**
1. **Operaciones** — estado del runner medido: 500/500, 0 fallos, 4,162
   archivos/s (rung 4 serializado), reglas v3.0-2026-09-19, llama-server up. [2]
2. **Facturas** — filtrar por NO_PAGAR; abrir una factura real con su traza
   (ej. `factura_8801.pdf`: NO_PAGAR por `NO_DOUBLE_PAYMENT`, duplicada de
   `2026-05-28_P005.pdf` — correcto incluso tras el reprocesado). [2][4]
3. **Revisión** — un escalado real con imagen de página y lectura candidata
   lado a lado (ej. `copia_2026_0518.pdf`, lectura VLM visible); explicar que
   Alberto acepta/edita con provenance y el motor recalcula. [3]
4. **Reglas** — versión v3.0-2026-09-19 y el what-if de umbrales (aviso
   honesto: el runner no registra confianza por campo, no se puede
   previsualizar sin re-medir). [2]

**Cierre del bloque**: «El sistema decide, Alberto supervisa. Nada se paga sin
regla que lo justifique; ante duda razonable, ESCALAR.» [4]

## 2. Arquitectura y ADRs (2 min) — la escalera con números medidos

**Diagrama** (PDF, sección Arquitectura — leer del PDF, no recitar):
PDF → extracción por página en escalera → parser (todas las candidatas) →
motor de reglas determinista → resultado + reglas que deciden; cada peldaño
escribe evidencia; store SQLite + ledger append-only; UI solo lectura.

**Los números de la escalera sobre el corpus real (500 PDFs, medido T10):**
- 471/500 (94,2 %) resuelven por capa de texto — el peldaño casi gratis;
  29 caen a raster; 0 solo-QR; 0 errores. [5]
- Latencia rung 1: media 0,4 ms, p95 2,0 ms. Rung 2 (raster+QR): media
  42,1 ms, p95 73,0 ms. [5]
- Rung 3 calibrado con el corpus (`extract-v2`): word-conf 40 y cobertura 0.4
  — la distribución es bimodal y el umbral 40 deja debajo exactamente los 3
  escaneos ilegibles que anuncia la doctrina (§11). [6]
- Rung 4 (VLM local, CPU, serializado): media 33,9 s/página, máx 60,1 s
  (n=28 invocaciones del lote 1 post-reprocesado — incluye timeouts de
  páginas difíciles, que escalan en vez de bloquear). [7]
- Rung 5 (nube, solo escalada): 29 invocaciones, media 1,6 s. [7]

**5 ADRs (uno por frasa):**
- ADR 01 — Motor determinista con reglas-como-datos v3→v4 (umbrales =
  configuración versionada, snapshot en cada decisión). [4]
- ADR 02 — Extracción en dos bloques, calibrada con el corpus (T10). [5][6]
- ADR 03 — Pipeline desacoplada; ERP fuera de scope con costura de adaptador;
  idempotencia (sha256, stage, versión). [8]
- ADR 04 — Trazabilidad completa en store (SQLite + ledger append-only). [8]
- ADR 05 — Rung 5 = deepseek-v4.1-flash (Qwen vetado, servidor caído);
  revisión humana NO bloqueante con overrides. [8][9]

## 3. Trazabilidad, escala y coste (4 min)

**Seguir UNA decisión real end-to-end** (elegida antes de la demo, apuntada
en el checklist): file_id → línea en `ledger.jsonl` con sus 13 códigos de
regla y su config_version → misma fila en `outcomes-lote1.jsonl` con
`invoice_id` (UUID estable) → evidencia por rung → decisión. Todo con
timestamp y hash; reprocesar el mismo lote es un no-op. [1][8]

**Reprocesado medido (reglas-como-datos v3→v4 en acción):** el fix T18
(ADR-06) re-decidió los 108 NO_PAGAR con warm cache a 111,26 files/s:
86 NO_PAGAR→PAGAR, 0 regresiones, validación OK, y la desviación esperada
documentada (factura_8801 sigue NO_PAGAR por NO_DOUBLE_PAYMENT — §6).
Distribución final: 433/22/45. [13]

**Trampas del corpus (auditoría T17 sobre el outcomes real):** [10]
- 3 proveedores fantasma (IBAN compartido) → ninguna pagada;
- duplicado FA-8801 → 2ª copia NO_PAGAR por NO_DOUBLE_PAYMENT;
- 7 facturas con instrucciones embebidas → 0 PAGAR;
- 26 escaneos ilegibles → 26 ESCALAR con confianza dudosa;
- outlier 84 700 € → ESCALAR.

**Escala — medido vs estimado:** [1][5][7]
- Primera corrida completa (500 archivos, rung 4 serializado): 4,162
  archivos/s medidos. Reprocesado del subset (108 NO_PAGAR) con warm cache:
  111,3 archivos/s medidos — idempotencia = no re-procesar lo bueno. [1][2][13]
- Throughput rung 1 solo: 2 636 archivos/s (dry-run, 2 workers). [5]
- Límite: lo marca el rung 4 (15,8 s/página serializado) — paralelizable si
  el hardware lo permite. Rung 1-2 son órdenes de magnitud más baratos. [7]
- Exactitud contra la referencia privada: **PENDIENTE-MEDICIÓN(T14-referencia)**;
  reprocesado tras el fix T18: impacto en cifras **PENDIENTE-MEDICIÓN**. [1][2]

**Fórmula de coste explícita** (T9, en el PDF §Escalabilidad): [9][7]
- `coste lote = electricidad CPU (h × kW × €/kWh; ESTIMADO) + llamadas cloud
  (nº × €/llamada; MEDIDO en corrida) + tokens de agentes (sin datos)`.
- Coste cloud del lote 1: **0,00 € medido** — 0 lecturas facturables (5
  intentos con 404 no facturan; credenciales cloud aún no inyectadas). [7]
- Electricity: CPU local — estimado 0,1 kW × 0,25 €/kWh. [9]
- Régimen completo MEDIDO (perfil de carga, T23): UI + 2 runners
  concurrentes + llama-server en la misma caja — la UI responde con peor p95
  < 12 ms (medido 7,7 ms con 500 facturas cargadas), 108–110 archivos/s por runner, RSS
  96/38 MB, 8 GB RAM libres, 0 ROJOS. [14]
- Escalabilidad de FORMATOS: emails/imágenes/Excel entran como nuevas fuentes
  de _features_ y reglas (T18/T13) — sin tocar el motor de reglas. [11]

## 4. Resiliencia (2 min) — drills en vivo si hay tiempo

**Cuatro drills automatizados, 4/4 PASS** (`.sdd/metrics/drills.json`, sin red
real, corren en segundos con `uv run python -m albertitos.drills`): [12]
- Proveedor rung 5 caído ⇒ la página queda ESCALAR con motivo en evidencia y
  el lote sigue (degradación, no aborte).
- 429 con Retry-After ⇒ backoff respetado (cap incluido), 0 llamadas extra.
- Crash del runner a mitad de lote ⇒ reanudación completa, 0 duplicados
  (idempotencia del store, T4).
- Ledger corrupto ⇒ el lector tolera y no inventa nada.

**En la pantalla Salud**: llama-server up (medido por el runner), drills
4/4, fallos/reintentos de proveedor. [2][12]

**Cierre**: «El sistema corre 24/7 desatendido: un crash pierde como mucho el
ítem en vuelo, un proveedor caído degrada la calidad pero no para el lote, y
cada decisión es reproducible byte a byte.»

---

## Checklist operativo (antes de la demo)

```bash
# 0. Desde la raíz del worktree; entorno ya sincronizado:
uv sync

# 1. (si aplica) llama-server para rung 4 — NO necesario para la UI:
#    health-check: curl -s http://127.0.0.1:8080/health
#    La UI lee su estado de .sdd/state/runner.json (medido por el runner),
#    no requiere el servicio vivo.

# 2. Store real del lote 1 (SOLO LECTURA) via symlink:
ln -sfn /home/deploy/fleet/w1/.sdd .sdd/lote1   # idempotente

# 3. Levantar la UI con el lote real:
ALBERTITOS_STORE=.sdd/lote1/ledger uv run uvicorn albertitos.ui.app:app --port 8000
# → http://127.0.0.1:8000  (Operaciones / Facturas / Revisión / Reglas / Salud)

# 4. PDF de la arquitectura (para la sección 2):
cd docs/report && ~/.local/bin/typst compile --font-path fonts albertitos_plan.typ
# (el PDF NO se commita: vive en el worktree para la demo)

# 5. Drills si hay tiempo (2 min, sin red):
uv run python -m albertitos.drills

# 6. Resumen ejecutivo para Alberto (PDF + HTML del paso 5):
uv run python -m albertitos.resumen \
    --store-root .sdd/lote1 \
    --maestro /home/deploy/hackspain26/caja-de-alberto/FINAL_v7_DEFINITIVO_ahorasi.xlsx \
    --salida resumen_alberto

# 7. Simulacro de defensa (verifica el guion contra el estado real):
uv run python -m albertitos.simulacro

# 8. Validador del entregable (si preguntan por el contrato):
uv run python -m albertitos.validate --outcomes .sdd/metrics/outcomes-lote1.jsonl \
    --facturas caja-de-alberto/facturas
```

**Factura marcada para la traza end-to-end**: elegir ANTES de la demo una
NO_PAGAR simple (duplicado FA-8801 es la más visual) y tener abierta su
página en Facturas → Detalle.

## Plan B (si algo falla en vivo)

- **UI caída / store inaccesible**: capturas del store real — las 5 pantallas
  responden 200 con el lote real (verificado con tests); re-lanzar uvicorn en
  otro puerto. Sin store externo, la UI sirve datos de prueba MARCADOS como
  tales (banner visible) — nunca se simula que son reales.
- **llama-server caído**: no afecta a la demo (la UI no lo necesita; su
  estado se muestra desde runner.json, medido por el runner).
- **Revisión sin imágenes para la factura elegida**: usar una con imagen de
  la cola (contador «con imagen disponible» en pantalla) — el resto degrada
  a la cadena de evidencia.
- **Números improvisados: PROHIBIDO.** Si un dato no está, se dice
  PENDIENTE y se señala dónde se medirá (T14/T13).

---

### Fuentes (los números existen en .sdd/metrics/ — nada de memoria)

- [1] `.sdd/metrics/lote1.json` (T14/T18): corrida original (500 archivos, 0 fallos, 347/108/45, 4.162 files/s) y distribucion_final tras el reprocesado (433/22/45, runner-1.1.0, 111,26 files/s en el subset).
- [2] `/home/deploy/fleet/w1/.sdd/state/runner.json` (leído por la UI):
  done=500, fallos=0, resultados 347/108/45, llama-server up, serializado.
- [3] `.sdd/lote1/review-queue/review.jsonl` (T14): cola de revisión real con
  campos, candidatas e imágenes por página.
- [4] `.sdd/metrics/outcomes-lote1.jsonl` (500 líneas) + ledger
  `.sdd/lote1/ledger/ledger.jsonl` (rule_codes por factura, trazable a
  invoice_id).
- [5] `.sdd/metrics/corpus-dryrun.json` (T10): 471/500 texto usable (94,2 %),
  29 raster, 0 QR, latencias por rung, 2 636 archivos/s, 3,57 s pared.
- [6] `.sdd/metrics/calibracion/calibracion-rung3.json` +
  `.sdd/metrics/calibracion.md` (T10): decisión extract-v2 (word-conf 40,
  cobertura 0.4), hueco bimodal, 3 ilegibles debajo.
- [7] `.sdd/metrics/lote1.json` → `rung4_vlm_local` (media 15 818 ms, máx
  33 725 ms, n=9) y `rung5_cloud` (9 invocaciones, media 524,6 ms).
- [8] `.sdd/lote1/store.db` + `.sdd/lote1/ledger/ledger.jsonl` (T4, store real
  del lote 1 en SOLO LECTURA): idempotencia y evidencia.
- [9] `docs/decisiones/DECISIONS.md` + AGENTS.md §13 (rung 5 deepseek-v4.1-flash,
  Qwen vetado) y `src/albertitos/metrics.py` (PRECIOS: electricidad estimada
  0,1 kW × 0,25 €/kWh; cloud nº × precio).
- [10] `.sdd/metrics/auditoria-trampas.md` (T17) y
  `.sdd/metrics/triage-revision.md` (T14): trampas VERDE y desglose de los 45
  escalados (RUNNER_TIMEOUT 20, mixto 14, NO_EMBEDDED_INSTRUCTIONS 5,
  DATE_VALID_NOT_FUTURE 3, PEDIDO_EN_REVISION 2, IBAN_MATCHES_MASTER 1).
- [11] `.sdd/backlog/closed/` (T13/T18): nuevas fuentes de datos y reglas
  como datos v3→v4 sin tocar el motor.
- [12] `.sdd/metrics/drills.json` (T12): 4/4 PASS con mediciones por drill.
- [14] `.sdd/metrics/perfil-carga.json` (T23): p95 por pantalla (peor 11,9 ms),
  108,7–110,0 archivos/s por runner, RSS ui 96 MB / runners 38 MB, RAM 12 GB
  total / 8 GB disponibles, 0 ROJOS.
- [13] `.sdd/metrics/impacto-fix-colapso.json` (T18): 500 archivos, 108 reprocesados, 86 NO_PAGAR→PAGAR, 0 regresiones, validación OK.

**Pendientes declarados**: exactitud contra referencia privada y reprocesado
post-fix (T18/T19) — PENDIENTE-MEDICIÓN(T14-referencia); coste por factura del
lote con credenciales cloud reales — PENDIENTE-MEDICIÓN.
