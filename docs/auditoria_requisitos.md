# Auditoría de requisitos — Maisa «500 Sombras de Alberto»

**Proyecto:** filemaid · **Repo:** `/home/deploy/hackspain26` · **Rama:** `feat/remotion-polish` · **Commit auditado:** `8a5fe33` (HEAD; re-auditoría «Re-auditoría 2026-09-20» al final de este doc revalida las medidas sobre `8a5fe33`: los commits posteriores a `7ace882` solo tocan `frontend/src/api.ts`, `docs/report/escalabilidad_datos.typ` y este doc — ningún entregable)
**Fecha:** 2026-09-20 · **Auditor:** AuditorReq (agente independiente). Reescritura completa del documento: todas las medidas de esta auditoría son propias, ejecutadas en esta sesión con `uv run python` (parseo programático, no muestreo a ojo).
**Contraste externo:** la rúbrica y los requisitos se contrastaron línea a línea contra https://hackathon.maisa.ai/ (la web cargó completa en esta sesión, 386 líneas de contenido leído). Coincide con la rúbrica reflejada aquí: 100 pts + 10 bonus, desempates escalabilidad → resiliencia → bonus, commit de cierre domingo 11:00, defensa de 10 min (2 demo + 2 arquitectura/ADRs + 4 trazabilidad/escala/coste + 2 resiliencia).

**Lectura global:** los 3 entregables están validados 1:1 y el **repo de entrega local existe** (`/home/deploy/delivery-repo`, raíz con exactamente los 3 ficheros, hashes idénticos al repo de solución). El único P0 binario que queda es **publicarlo en GitHub con remoto configurado y teamId** — hoy el delivery-repo no tiene ningún `remote`.

---

## 1. Entregables (contrato §1 de AGENTS.md; web: «Tres archivos. Un repositorio»)

La web exige: repo **público de GitHub separado** de la solución, raíz con **exactamente** `outcomes.jsonl`, `outcomes_lote2.jsonl`, `albertitos_plan.pdf`, sin código/credenciales/ejecutables, teamId compartido, y cierre domingo 11:00.

### 1.1 Verificación por entregable [medido, esta sesión]

| Entregable | Estado | Evidencia |
|---|---|---|
| `outcomes.jsonl` | ✅ **CUMPLE** | 500 líneas [wc -l]. Parseo programático (`json.loads` por línea, `uv run python`): 500/500 JSON válido, claves exactamente `{file_id, result}` (0 campos extra), `file_id` = basename exacto sin `/` ni `\` (500/500), `result ∈ {PAGAR, NO_PAGAR, ESCALAR}` (500/500), 0 duplicados (500 únicos). Cobertura exacta contra `caja-de-alberto/facturas/` (500 PDFs en disco): missing=∅, extra=0. Distribución: **PAGAR 433 / NO_PAGAR 22 / ESCALAR 45**. |
| `outcomes_lote2.jsonl` | ✅ **CUMPLE** | 40 líneas [wc -l]. Mismo parseo programático: 40/40 válidas, claves exactas, basename exacto, dominio de resultados correcto, 0 duplicados, 0 solapamiento con el lote 1. Cobertura exacta contra `caja-de-alberto/facturas_primin/` (40 PDFs): missing=∅, extra=0. Distribución: **PAGAR 26 / NO_PAGAR 11 / ESCALAR 3**. |
| `albertitos_plan.pdf` | ✅ **CUMPLE** (recompilado) | En raíz: **149 321 bytes, 15 páginas** [stat + pypdf], mtime 2026-09-20 01:57:46, **byte-idéntico** a `docs/report/albertitos_plan.pdf` (misma fecha 01:57:22 — se copió tras recompilar). Contenido verificado con pypdf: portada «FILEMAID PLAN» pág. 1; **«3 Escalabilidad y coste» en la pág. 6** con «La escalabilidad de filemaid no se afirma: se mide.» y la sección «Resiliencia» en la misma pág. 6; **ADR-01 en pág. 10**, **ADR-08 en pág. 15** (numeración física del PDF; el pie de página interno va desfasado −1); mitigación del rango de ADRs en **pág. 15**: «Los 8 ADRs anteriores son ADICIONES INCREMENTALES, no una lista cerrada…». NOTA: la auditoría anterior citaba 16 págs/139 577 bytes — el PDF se recompiló desde entonces; las medidas vigentes son las de arriba. |

### 1.2 Repo de entrega separado — ✅ existe localmente / ❌ sin publicar

Encontrado en **`/home/deploy/delivery-repo`** (git repo, branch `master`, 4 commits, último `4fbb881` «Entrega: sincroniza los 3 entregables con el contrato exacto {file_id, result} y añade el lote 2»). Verificado:

- **Raíz con EXACTAMENTE los 3 ficheros** [ls -A]: `albertitos_plan.pdf`, `outcomes.jsonl`, `outcomes_lote2.jsonl` + `.git/`. Sin README, sin código, sin credenciales.
- **Hashes idénticos al repo de solución** [sha256sum, medido]:
  - `outcomes.jsonl` → `67a1acea40b48813c60753d1da6d7adeb9492acda3c2132491a095b1403a0eb7`
  - `outcomes_lote2.jsonl` → `34d55cb41c8bcece40e4e7c5e2fb75bf5c16b844d9ac766c215783e775d0fc4b`
  - `albertitos_plan.pdf` → `c64db1be58ea0d5d1939a325dcc3ee826712f7db4c7b7257a5d58b50d3466cc6`
- ❌ **Sin ningún `remote` configurado** (`git remote` → 0 líneas): **no es público ni está en GitHub**. Es el único P0 binario restante (web: «Compartid el teamId y la URL pública de GitHub»).

### 1.3 ADRs — 8 declarados vs rango pedido 2–5 (riesgo conocido, mitigado)

`docs/report/albertitos_plan.typ` declara **8 ADRs** [grep -c '#adr(' → 8, líneas 29–92; verificados por lectura: ADR-01 motor de reglas determinista, ADR-02 features/parser, ADR-03 pipeline Python con costura ERP, ADR-04 trazabilidad en BD, ADR-05 rung cloud + revisión humana, ADR-06 selección de candidato con provenance, ADR-07 escritorio pywebview, ADR-08 `outcomes.on_fail`]. La web pide «entre 2 y 5 decisiones relevantes»; el propio PDF mitiga el exceso en su pág. 15. Estado: **PARCIAL** (contenido completo y estructurado — contexto/alternativas/decisión/consecuencias/evidencia verificados en los 8; el riesgo es solo de conteo si el jurado es estricto).

---

## 2. Rúbrica del tribunal (100 + 10 pts — contrastada con la web en esta sesión)

### 2.1 Producto, arquitectura y ADRs — 35 pts · ✅ CUMPLE (con el riesgo de conteo de §1.3)

- Arquitectura y ADRs en `docs/report/albertitos_plan.typ` → compilados en `albertitos_plan.pdf` (15 págs, escalabilidad y resiliencia en pág. 6, ADRs págs. 10–15) [pypdf, medido].
- **ADR-05 sin placeholders**: 0 ocurrencias de `PENDIENTE-MEDICIÓN` [grep]; la evidencia de ADR-05 (líneas 65–71 del .typ) cita ahora los números medidos del lote 1 — 45 de 500 ESCALAR con desglose por regla (5 `NO_EMBEDDED_INSTRUCTIONS`, 3 `DATE_VALID_NOT_FUTURE`, 2 `PEDIDO_EN_REVISION`, 1 `IBAN_MATCHES_MASTER`, resto por desacuerdo de evidencia) y los 4 drills PASS. Cerrado en `054aebe`.
- ⚠️ Menor: ADR-05 y el desglose citan `NO_EMBEDDED_INSTRUCTIONS` y `PEDIDO_EN_REVISION`, que son **códigos históricos** de la evidencia (el motor actual declara 8 códigos; ver §2.2). La nota `video/data_outcomes_lote1_NOTA.md` lo documenta y da la réplica si el tribunal pregunta.
- `docs/decisiones/DECISIONS.md` existe (citado por ADR-05 como registro de la decisión).

### 2.2 Trazabilidad y observabilidad — 20 pts · ✅ CUMPLE (provenance histórica documentada)

- Cadena input→resultado trazable en código: `ExtractionFeature`/`ExtractionField` con `values[]` por candidato (`src/filemaid/types.py`), veredictos PASS/FAIL/UNKNOWN con motivo y provenance, `RULE_CODES` con las **8 reglas v3** en `src/filemaid/rules/rules.py:320` [verificado esta sesión por lectura].
- La decisión real de demo (factura_8801 duplicada → `NO_DOUBLE_PAYMENT:FAIL` → NO_PAGAR) y las señales operativas (`/api/salud`, `/api/jobs`, `/api/trazas`, `/api/reprocesar/{file_id}`) siguen en pie (auditorías previas, sin cambios desde `65f3ce4`).
- **Provenance del JSONL de evidencia del lote 1** (`video/data_outcomes_lote1.jsonl`): **RESUELTA POR DOCUMENTACIÓN**. La nota `video/data_outcomes_lote1_NOTA.md` (leída íntegra esta sesión) documenta: mezcla `runner-1.0.0` (392) / `runner-1.1.0` (108), `config_version` uniforme `v3.0-2026-09-19`, 13 códigos históricos vs 8 actuales con mapeo explícito (`ORDER_AMOUNT_MATCHES` = alias interno del cruce de importe en `OrderBelongsToSupplier`; `NO_EMBEDDED_INSTRUCTIONS`, `PROVEEDOR_FANTASMA`, `AMOUNT_OUTLIER`, `PEDIDO_EN_REVISION` aspiracionales, **ninguno con FAIL registrado** en las 500 filas), y las razones medidas por las que NO se regeneró (el store local solo cubre 379/500 file_ids del lote 1; regenerar exigiría ~121 extracciones VLM y arriesgaría la distribución 433/22/45 fijada en el vídeo). El entregable no se afecta (export = `{file_id, result}`, 0 campos extra medidos en §1.1).

### 2.3 Escalabilidad y coste — 25 pts · ✅ CUMPLE

- «3 Escalabilidad y coste» en el PDF entregable (pág. 6): hardware real de la máquina, throughput por escalón, límites prácticos y coste con etiquetas medido/estimado/no-medido; apertura «La escalabilidad de filemaid no se afirma: se mide.» [pypdf, medido].
- Fuente: `docs/report/escalabilidad.typ` consume `escalabilidad_datos.typ` (generado por `filemaid.metrics`) y resume `docs/capacidad_y_coste.md` + `docs/benchmarks_extraccion.md` (auditorías previas; sin cambios relevantes desde `96eeeb9`).
- La defensa pide además «qué cambiaría con emails, imágenes o Excel» — el plan de nuevos tipos está en el PDF (escalera de 7 rungs + ADR-03 para nuevos formatos). El conector xlsx directo sigue sin existir (`master.py` es CSV-only, P3 de auditorías previas): explicación preparada, no código.

### 2.4 Resiliencia y recuperación — 10 pts · ✅ CUMPLE

- Estado en disco (PouchDB/LevelDB), idempotencia por `(sha256, stage, engine_version, config_version)`, export atómico solo con lote completo, degradación rung a rung con `skipped:<reason>`, cloud jamás automático (auditorías previas; sin cambios desde `65f3ce4`).
- **Retry/Retry-After en el rung cloud conciliado con el código** desde `65f3ce4`: `_MAX_ATTEMPTS=3`, `_is_retryable()` (429 y 5xx), `_retry_delay_s()` (Retry-After con cap 30 s; si no 1/2/4 s) en `src/filemaid/extract/rungs/cloud_vlm.py`, verificado por lectura completa en la re-auditoría del addendum y sin commits que lo toquen desde entonces [git log]. `tests/test_openai_rung.py` → 11 passed [medido en esa sesión].
- Drill `backoff-429` (429×2, Retry-After respetado, 3 llamadas exactas) y `crash-reanudacion` PASS en `video/data_drills.json`, byte-idéntico a `.sdd/metrics/drills.json` [cmp medido en addendum].
- La defensa exige «explicad o demostrad un timeout, rate limit, respuesta inválida o caída del proveedor» — el drill `rung5-provider-caido` cubre la caída.

### 2.5 Calidad de ejecución — 10 pts · ✅ CUMPLE

- Arranque de un paso `./run.sh [app|vlm|desktop]` + `start.py` (stdlib only); app de escritorio pywebview compartiendo UI Vue y motor (ADR-07); watcher con notificación ESCALAR y reintento de entregas fallidas; pulido de flujo frecuente (sync topbar, auto-refresco, confirmación en revisión).
- 40 ficheros de tests; `pytest tests/test_rules_engine.py` → 17 passed y `tests/test_openai_rung.py` → 11 passed [medidos en sesiones de auditoría previas, sin cambios de código en esas rutas desde entonces].
- UI en español con cola de revisión, reglas visibles e informe HTML de la frontera NO_PAGAR/ESCALAR.

### 2.6 Bonus: mejora adicional para Alberto — +10 · ✅ CUMPLE (implementada y mostrada)

- **Vídeo entregable verificado en esta sesión**: `video/out/filemaid.mp4` — **8 597 508 bytes**, átomo `mvhd` v0: timescale 1000, duration **180 000 → 180,000 s exactos** [medido por parseo del átomo, esta sesión]. Coincide con el commit `7ace882` («portada dedicada a Alberto… ffprobe 8 597 508 bytes»). Verificación visual de las 8 escenas cerrada en el addendum del render `5ef8fa3` (stills `video/out/verify-escena{1..8}.png`); este render final añade la portada dedicada con su propia verificación (`video/out/verify-portada-final.png`).
- La mejora (vigilante + notificación ESCALAR con provenance y reintento) está implementada (`src/filemaid/desktop/watcher.py`) y mostrada en el vídeo (escena 3). Cumple los criterios de la web: «original, implementada y mostrada», no cosmética, no parte necesaria del flujo principal.

---

## 3. Lote 2 «sorpresa» (sábado 18:00 — web: +40 facturas, ERP actualizado, regla nueva)

| Requisito (web) | Estado | Evidencia |
|---|---|---|
| +40 facturas nuevas | ✅ Corrido y contrastado | `outcomes_lote2.jsonl` 40/40, 26/11/3, cobertura exacta [medido, §1.1]. |
| ERP actualizado | ✅ Datos presentes | `erp_export_lote2.csv`, `pedidos_nuevos.csv`, `proveedores_nuevos.csv` en el submódulo [auditorías previas]. Nota de arquitectura abierta: no hay cliente HTTP del ERP en `src/filemaid/` — costura manual a explicar en la defensa. |
| Conservar el trabajo | ✅ Por diseño y probado | Idempotencia + drill `crash-reanudacion` PASS. |
| Reprocesar tras el cambio | ✅ Ejercitado | Reprocesado del lote 1 tras ADR-06 (108 ficheros, 86 → PAGAR, 0 regresiones) en `video/data_impacto.json` [auditorías previas]. |
| Regla nueva (v4) | 🔄 Borrador listo, activación pendiente del enunciado del sábado | `master/rules.yaml` contiene la sección raíz `borrador_v4` (`enabled: false`, código `PEDIDO_EN_REVISION`, FAIL → ESCALAR) [grep → 1, verificado esta sesión]. Activar exige ADR + clase en `RULE_CODES`/`_RULE_IMPLS` + `rules.enabled`. Hueco de preparación principal: el enunciado exacto del sábado no se conoce aún. |

---

## 4. Validación JSONL — resumen ejecutivo (parseo programático, esta sesión)

| Check | `outcomes.jsonl` | `outcomes_lote2.jsonl` |
|---|---|---|
| Líneas | **500** | **40** |
| JSON válido por línea (`json.loads`) | 500/500 | 40/40 |
| Claves exactamente `{file_id, result}` (0 extra) | 500/500 | 40/40 |
| `file_id` = nombre exacto del PDF, sin ruta | 500/500 | 40/40 |
| `result ∈ {PAGAR, NO_PAGAR, ESCALAR}` | 500/500 | 40/40 |
| `file_id` únicos / duplicados | 500 / 0 | 40 / 0 |
| Cobertura exacta vs PDFs en disco (missing/extra) | ∅ / 0 (500 PDFs en `caja-de-alberto/facturas/`) | ∅ / 0 (40 PDFs en `caja-de-alberto/facturas_primin/`) |
| Distribución | **PAGAR 433 / NO_PAGAR 22 / ESCALAR 45** | **PAGAR 26 / NO_PAGAR 11 / ESCALAR 3** |
| Solapamiento lote1 ∩ lote2 | — | 0 |

En la copia del delivery-repo: mismos hashes sha256 → la validación es idéntica a la copia entregada.

---

## 5. Hallazgos críticos

1. **P0 — Repo de entrega sin publicar**: `/home/deploy/delivery-repo` es correcto (raíz exacta de 3 ficheros, hashes idénticos) pero **no tiene ningún `git remote`** — no está en GitHub, no es público, y no hay forma de que la organización lo clone. La web exige compartir teamId + URL pública; cierre domingo 11:00. Acción: crear repo público en GitHub, `git remote add`, push, teamId en la descripción.
2. **P0 — teamId no verificable desde aquí**: la entrega exige teamId visible (descripción del repo). Pendiente manual del equipo junto con el push.
3. **PARCIAL — 8 ADRs vs rango pedido 2–5**: contenido completo y mitigado por texto en el propio PDF (pág. 15), pero si el jurado es estricto con el conteo podría penalizar el criterio de 35 pts. Decidir en la defensa: mantener la mitigación o recortar la numeración presentada.
4. **MENOR — Códigos históricos en ADR-05 y trazas**: ADR-05 y la evidencia del lote 1 citan códigos (`NO_EMBEDDED_INSTRUCTIONS`, `PEDIDO_EN_REVISION`, `ORDER_AMOUNT_MATCHES`) que el motor actual no declara (8 reglas). Documentado y con réplica en `video/data_outcomes_lote1_NOTA.md` (ningún FAIL registrado de los 4 aspiracionales; distribución real 433/22/45). No afecta al entregable (JSONL = `{file_id, result}` verificado).
5. **MENOR — Costura ERP sin cliente HTTP**: el ERP del lote 2 se consumió con maestros CSV fusionados; no hay cliente HTTP del ERP en `src/filemaid/`. Explicable en defensa; no es requisito de la web.
6. **INFO — PDF recompilado**: el entregable cambió respecto a la auditoría anterior (16→15 págs, 139 577→149 321 bytes, escalabilidad en pág. 6 en lugar de 7). Contenido verificado íntegro; cualquier material de apoyo que cite «pág. 7» debe actualizarse a «pág. 6».

---

## 6. Checklist de entrega final (domingo 11:00)

- [ ] **P0** Crear el repo público de GitHub y añadir el remote a `/home/deploy/delivery-repo`; push de `master` (4 commits listos).
- [ ] **P0** teamId en la descripción del repo; URL compartida con la organización antes de las 11:00.
- [ ] **P0** Post-push: `sha256sum` remoto vs `67a1acea…` / `34d55cb4…` / `c64db1be…` y re-ejecutar el parseo de §4 sobre los ficheros clonados.
- [ ] **P1** Sábado: activar `borrador_v4` según el enunciado real (ADR + código + `rules.enabled`), correr `make erp-lote2`, decidir reprocesos.
- [ ] **P1** Ensayar la demo de 10 min: decisión end-to-end (factura_8801), escalabilidad pág. 6, mitigación ADRs pág. 15, drill `backoff-429` / `rung5-provider-caido`.
- [ ] **P2** Actualizar cualquier material de apoyo que cite «pág. 7 del PDF» → «pág. 6» (hallazgo 6).

---

*Auditoría base ejecutada el 2026-09-20 sobre `7ace882` por AuditorReq. Medidas propias de esa sesión: parseo programático de ambos JSONL (540/540 líneas válidas, 0 incidencias), cobertura exacta contra los directorios de PDFs, pypdf sobre `albertitos_plan.pdf` (15 págs, escalabilidad pág. 6, ADRs págs. 10–15, mitigación pág. 15), grep de ADRs y placeholders en `albertitos_plan.typ` (8 ADRs, 0 placeholders), lectura de ADR-05, verificación de `/home/deploy/delivery-repo` (raíz exacta, hashes, sin remote), lectura íntegra de `video/data_outcomes_lote1_NOTA.md`, parseo `mvhd` del vídeo (180,000 s, 8 597 508 bytes) y contraste de la rúbrica contra https://hackathon.maisa.ai/ (cargada completa). No se ejecutaron suites completas, formateadores ni lint (restricción de la asignación). La revalidación independiente sobre `8a5fe33` está en la sección siguiente.*

## 7. Re-auditoría 2026-09-20 (independiente, sobre `8a5fe33`)

**Alcance:** revalidación completa del estado ACTUAL del repo (`8a5fe33`, árbol limpio, working tree sin modificaciones) y de la copia de entrega en `/home/deploy/delivery-repo`. Todas las medidas de esta sección son propias, ejecutadas en esta sesión.

### 7.1 Parseo programático de los 2 JSONL en `/home/deploy/delivery-repo` [medido]

Script `uv run python` (json.loads línea a línea + comparación contra `os.listdir` de los PDFs en disco del repo de solución):

| Check | `outcomes.jsonl` | `outcomes_lote2.jsonl` |
|---|---|---|
| Filas / JSON válido | 500/500 | 40/40 |
| Claves exactamente `{file_id, result}` | 500/500 | 40/40 |
| `file_id` basename exacto terminado en `.pdf` | 500/500 | 40/40 |
| `result ∈ {PAGAR, NO_PAGAR, ESCALAR}` | 500/500 | 40/40 |
| Duplicados | 0 | 0 |
| Cobertura vs PDFs en disco (missing/extra) | 0/0 (500 PDFs, todos `.pdf`, en `caja-de-alberto/facturas/`) | 0/0 (40 PDFs, todos `.pdf`, en `caja-de-alberto/facturas_primin/`) |
| Distribución | PAGAR 433 / NO_PAGAR 22 / ESCALAR 45 | PAGAR 26 / NO_PAGAR 11 / ESCALAR 3 |
| Solapamiento lote1 ∩ lote2 | — | **0** |

**Incidencias: 0** (ni claves extra, ni file_ids con ruta, ni resultados fuera de dominio). Idéntico al resultado de la auditoría base sobre la copia del repo de solución.

### 7.2 Hashes sha256 de la entrega [medido]

```
$ cd /home/deploy/delivery-repo && sha256sum *
c64db1be58ea0d5d1939a325dcc3ee826712f7db4c7b7257a5d58b50d3466cc6  albertitos_plan.pdf
67a1acea40b48813c60753d1da6d7adeb9492acda3c2132491a095b1403a0eb7  outcomes.jsonl
34d55cb41c8bcece40e4e7c5e2fb75bf5c16b844d9ac766c215783e775d0fc4b  outcomes_lote2.jsonl
```

Los 3 coinciden con los esperados. Además, `sha256sum docs/report/albertitos_plan.pdf` en el repo de solución → `c64db1be…` **idéntico** al de la entrega (byte-idénticos). Estado git del delivery-repo: branch `master`, 4 commits, último `4fbb881`, working tree limpio. `git remote` → **0 líneas** (P0 sigue abierto, §7.4).

### 7.3 Contraste requisito a requisito contra https://hackathon.maisa.ai/ [medido, web recargada esta sesión — 395 líneas]

La web no ha cambiado desde la auditoría base: misma rúbrica (100 + 10), mismos plazos (cierre domingo 20 a las 11:00, lote 2 sábado 18:00, defensa 10 min: 2+2+4+2). Contraste de CADA requisito:

| # | Requisito (web) | Evidencia en repo | Veredicto |
|---|---|---|---|
| 1 | Raíz con **exactamente** `outcomes.jsonl`, `outcomes_lote2.jsonl`, `albertitos_plan.pdf`, sin código/credenciales/ejecutables | `ls -A` delivery-repo: exactamente esos 3 ficheros + `.git/` [medido] | ✅ |
| 2 | Contrato JSONL: `file_id` = nombre exacto del PDF, `result` ∈ {PAGAR, NO_PAGAR, ESCALAR}, un objeto por factura | §7.1: 540/540, 0 incidencias [medido] | ✅ |
| 3 | Validación obligatoria: registro único por archivo de ambos lotes (referencia privada de la org) | Unicidad 540/540, cobertura exacta 500+40 [medido] | ✅ (aptitud final la decide la org; la estructura es perfecta) |
| 4 | `albertitos_plan.pdf`: Arquitectura + **de 2 a 5 ADRs** con contexto/alternativas/decisión/consecuencias/evidencia | 15 págs [pypdf medido], **8 ADRs declarados** vs rango 2–5, mitigados por texto en pág. 15 | ⚠️ PARCIAL (hallazgo 3) |
| 5 | Rúbrica — Producto/arquitectura/ADRs (35) | §2.1; PDF: «3 Escalabilidad y coste» en pág. 6 re-verificado con pypdf esta sesión | ✅ (con riesgo de conteo del #4) |
| 6 | Rúbrica — Trazabilidad y observabilidad (20) | §2.2; señales `/api/salud`, `/api/jobs`, `/api/trazas`, `/api/reprocesar/{file_id}`; nota de provenance del lote 1 | ✅ |
| 7 | Rúbrica — Escalabilidad y coste (25) | §2.3; sección 3 del PDF (pág. 6) + `docs/capacidad_y_coste.md` + `docs/benchmarks_extraccion.md` | ✅ |
| 8 | Rúbrica — Resiliencia y recuperación (10) | §2.4; retry 429/5xx verificado por lectura; drills `backoff-429` y `crash-reanudacion` PASS | ✅ |
| 9 | Rúbrica — Calidad de ejecución (10) | §2.5; `./run.sh`, desktop pywebview, watcher con notificación ESCALAR | ✅ |
| 10 | Rúbrica — Bonus mejora adicional (+10) | §2.6; watcher + notificación ESCALAR, implementada y mostrada en el vídeo (8 597 508 B / 180 s) | ✅ |
| 11 | Lote 2: +40 facturas | §7.1 fila lote2: 40/40, cobertura exacta [medido] | ✅ |
| 12 | Lote 2: ERP actualizado | `erp_export_lote2.csv`, `pedidos_nuevos.csv`, `proveedores_nuevos.csv` presentes en `caja-de-alberto/` [medido]; sin cliente HTTP del ERP en `src/filemaid/` (hallazgo 5) | ✅ |
| 13 | Lote 2: conservar el trabajo | Idempotencia + drill `crash-reanudacion` PASS | ✅ |
| 14 | Lote 2: reprocesar lo afectado | Reprocesado del lote 1 tras ADR-06 (108 ficheros, 86 → PAGAR, 0 regresiones) | ✅ |
| 15 | Lote 2: regla nueva (v4) | Borrador `borrador_v4` (`enabled: false`) en `master/rules.yaml`; activación pendiente del enunciado real | 🔄 PREPARADO |
| 16 | **teamId + URL pública de GitHub** (paso 01 de la entrega) | `git remote` → 0 líneas; sin publicar; teamId no verificable | ❌ **P0 abierto** |
| 17 | No subir código/credenciales/ejecutables al repo de entrega | Raíz exacta de 3 ficheros [medido] | ✅ |

### 7.4 Hallazgos de la re-auditoría

1. **P0 (sigue abierto) — Repo de entrega sin publicar**: `git remote` en `/home/deploy/delivery-repo` sigue devolviendo 0 líneas [medido esta sesión]. Sin push no hay URL pública que compartir; cierre domingo 11:00.
2. **P0 (sigue abierto) — teamId no verificable**: la entrega exige teamId + URL; nada en el repo puede demostrarlo. Pendiente manual junto con el push.
3. **PARCIAL (sin cambios) — 8 ADRs vs rango 2–5**: reconfirmado por lectura del `.typ`; mitigación en pág. 15 del PDF.
4. **MENOR (sin cambios) — Códigos históricos** en ADR-05 y evidencia del lote 1; documentado en `video/data_outcomes_lote1_NOTA.md`.
5. **MENOR (sin cambios) — Costura ERP sin cliente HTTP**: los CSV del lote 2 están en disco [re-confirmado], pero no hay cliente HTTP del ERP en `src/filemaid/`.
6. **NUEVO INFO — Cambios en `8a5fe33` no afectan a entregables**: `git diff --stat 19aebd8..8a5fe33` = `frontend/src/api.ts` (fix P0 de auth del cliente), `docs/report/escalabilidad_datos.typ` (se elimina una línea comentada residual de T13/T14) y `docs/auditoria_requisitos.md` (corrección de paginación de ADRs: págs. 9–14 → 10–15). **Diferencia vs auditoría previa:** solo esta corrección de paginación; ningún número medido cambió.

**Diferencias totales vs la auditoría previa:** ninguna en datos medidos. Únicas diferencias: (a) corrección de paginación del PDF (ADRs en págs. 10–15, no 9–14) ya incorporada; (b) commit auditado avanza de `19aebd8` a `8a5fe33` sin tocar entregables. Los 2 P0 (remote GitHub + teamId) permanecen abiertos y siguen siendo los únicos bloqueantes de la entrega.

### 7.5 Estado de la checklist tras la re-auditoría

## 8. Re-auditoría 2026-09-20 (tercera pasada, sobre `6bc93ac` — AuditorWorker)

**Alcance:** actualización a la realidad ACTUAL del repo tras la ola de trabajo en curso (watcher, UI, benchmarks de coste, re-render del vídeo). Todas las medidas de esta sección son propias, ejecutadas en esta sesión con `uv run python`. La web https://hackathon.maisa.ai/ fue recargada íntegra (395 líneas): rúbrica sin cambios — 100 pts + 10 bonus (35/20/25/10/10), desempates escalabilidad → resiliencia → bonus, lote 2 sábado 18:00, cierre domingo 11:00, defensa 10 min (2+2+4+2), contrato JSONL `{"file_id":"...","result":"..."}` con `file_id` = nombre exacto del PDF.

### 8.1 Estado del árbol [medido]

- `git rev-parse HEAD` → `6bc93acac1b184ebe0166032f923126506bb3d92` (2026-09-20 04:02:49 +0000). Working tree con cambios SIN commitear en curso: `src/filemaid/desktop/watcher.py` (+6, expone `poll_interval`/`last_scan` en estado), `tests/test_desktop_watcher.py` (+84), `frontend/src/App.vue`/`InvoiceDrawer.vue`/`nav.ts` (badge de revisión pendiente), `scripts/bench_vlm_local.py` + `docs/benchmark_local_vs_remoto.md` (nuevo) + 3 `data/bench_vlm_local_*.json`, `video/*` y `frontend/src/api.ts` (tarea 8, otra sesión). Ningún cambio toca los 3 entregables de la raíz (deliberadamente en `.gitignore:33-41`; viven en el delivery-repo).
- Tests: **40 ficheros en `tests/`, 295 funciones `def test`** [medido con grep].

### 8.2 Validación de los 2 JSONL (parseo programático propio) [medido]

Script `uv run python` (json.loads por línea + `os.listdir` de los PDFs en disco):

| Check | `outcomes.jsonl` | `outcomes_lote2.jsonl` |
|---|---|---|
| Líneas / JSON válido | 500/500 | 40/40 |
| Claves exactamente `{file_id, result}` | 500/500 | 40/40 |
| `file_id` basename exacto (sin `/` ni `\`) | 500/500 | 40/40 |
| `result ∈ {PAGAR, NO_PAGAR, ESCALAR}` | 500/500 | 40/40 |
| Únicos / duplicados | 500 / 0 | 40 / 0 |
| Cobertura vs PDFs en disco (missing/extra) | 0/0 (500 PDFs en `caja-de-alberto/facturas/`) | 0/0 (40 PDFs en `caja-de-alberto/facturas_primin/`) |
| Distribución | **PAGAR 433 / NO_PAGAR 22 / ESCALAR 45** | **PAGAR 26 / NO_PAGAR 11 / ESCALAR 3** |

Solapamiento lote1 ∩ lote2: **0**. Incidencias totales: **0**.

### 8.3 Entregables y hashes [medido]

- Raíz del repo de solución: los 3 ficheros presentes con hashes **idénticos** a la copia de entrega `/home/deploy/delivery-repo` [sha256sum en ambas copias]:
  - `outcomes.jsonl` → `67a1acea40b48813c60753d1da6d7adeb9492acda3c2132491a095b1403a0eb7`
  - `outcomes_lote2.jsonl` → `34d55cb41c8bcece40e4e7c5e2fb75bf5c16b844d9ac766c215783e775d0fc4b`
  - `albertitos_plan.pdf` → `c64db1be58ea0d5d1939a325dcc3ee826712f7db4c7b7257a5d58b50d3466cc6` (149 321 B, **15 págs** [pypdf]; byte-idéntico a `docs/report/albertitos_plan.pdf`, también 15 págs).
- Delivery-repo: raíz con EXACTAMENTE los 3 ficheros + `.git/` [ls -A], 4 commits (último `4fbb881`), `git remote` → **0 líneas** (P0 sigue abierto, §8.7).
- OJO operacional: `albertitos_plan.pdf`, `outcomes*.jsonl` y `docs/report/*.pdf` están en `.gitignore` (líneas 33-41, por diseño: los compilables viven en el delivery-repo) y `video/out/filemaid.mp4` está trackeado. Cualquier sincronización futura al delivery-repo debe hacerse copiando ficheros, no vía git.

### 8.4 albertitos_plan.pdf — contenido [medido con pypdf]

- 15 páginas. «Escalabilidad» aparece en págs. 2, 6 y 11; la sección «Escalabilidad y coste» y «Resiliencia» en la **pág. 6**; la mitigación de conteo de ADRs («el jurado puede leer los ADR-01–05 como el núcleo arquitectónico y los ADR-06–08 como extensiones») en la **pág. 15**.
- **8 ADRs declarados** [grep -c '#adr(' docs/report/albertitos_plan.typ → 8], 0 placeholders `PENDIENTE-MEDICIÓN`. Estructura contexto/alternativas/decisión/consecuencias/evidencia verificada por lectura de las citas extraídas (ADR-01 configuración versionada por campo, ADR-06 auditoría por candidato, ADR-08 `outcomes.on_fail`). **Sigue PARCIAL por conteo** (web: «de 2 a 5 decisiones relevantes»), con la mitigación dentro del propio PDF.
- Comprobación adversarial sobre mi propio muestreo de la auditoría previa: ADR-03/04/05 no caen en mis páginas muestreadas porque pypdf no extrae sus encabezados de sección como texto `ADR-0N` (los encabezados están en mayúsculas al inicio de página); el recuento fuente de verdad es el grep del `.typ` (8) y las menciones extraídas — no un hueco de contenido. Verificado ADR-05 por lectura en auditorías previas (sin placeholder, con números medidos del lote 1).

### 8.5 Bonus: vídeo re-renderizado (CAMBIO desde la auditoría previa) [medido]

- `video/out/filemaid.mp4`: **8 549 736 bytes** (antes 8 597 508), mvhd v0 timescale 1000, duration **180 000 → 180,000 s exactos** [parseo propio del átomo en esta sesión]. Diff sin commitear también en `video/src/FilemaidVideo.tsx`, `video/src/scenes.ts`, `video/GUION.md`, `video/README.md` (trabajo en curso de VideoWorker). Veredicto sobre el BONUS (mejora para Alberto: watcher + notificación ESCALAR con provenance y reintento): **CUMPLE igualmente** — la mejora sigue implementada en `src/filemaid/desktop/watcher.py` y el vídeo mantiene 180,000 s; el re-render es cosmético respecto a la rúbrica. Pendiente de commit y (si el equipo lo pide) re-verificación con ffprobe tras commitar.
- Drills [video/data_drills.json, medido]: 4/4 PASS (`rung5-provider-caido`, `backoff-429`, `crash-reanudacion`, `ledger-corrupto`).

### 8.6 Rúbrica — veredicto por criterio (evidencia de esta sección)

| Criterio | Veredicto | Evidencia clave |
|---|---|---|
| Producto, arquitectura y ADRs (35) | ✅ CUMPLE con ⚠️ riesgo de conteo | §8.4: 15 págs, escalabilidad pág. 6, 8 ADRs mitigados en pág. 15 |
| Trazabilidad y observabilidad (20) | ✅ CUMPLE | §8.2; 8 reglas v3, señales `/api/salud|jobs|trazas|reprocesar`; provenance lote 1 documentada (nota dedicada) |
| Escalabilidad y coste (25) | ✅ CUMPLE | PDF pág. 6 + `docs/capacidad_y_coste.md` + benchmarks nuevos en curso (`docs/benchmark_local_vs_remoto.md`, 3 JSON en `data/`) — refuerzan el criterio |
| Resiliencia y recuperación (10) | ✅ CUMPLE | Drills 4/4 PASS [§8.5]; retry `_MAX_ATTEMPTS=3` + Retry-After en `cloud_vlm.py` (sin commits que lo toquen desde `65f3ce4`) |
| Calidad de ejecución (10) | ✅ CUMPLE | 40 ficheros de test / 295 tests [medido §8.1]; watcher con reintento y nuevo estado observable (`poll_interval`, `last_scan`) |
| Bonus mejora adicional (+10) | ✅ CUMPLE | Watcher + notificación ESCALAR, implementada y mostrada en vídeo de 180,000 s [§8.5] |
| Contrato JSONL y cobertura | ✅ CUMPLE | 540/540 filas válidas, 0 incidencias, cobertura exacta, 0 solapes [§8.2] |
| Repo de entrega público + teamId | ❌ NO_CUMPLE | `git remote` → 0 líneas; teamId no verificable [§8.3] |

### 8.7 Hallazgos de esta pasada

1. **P0 (abierto) — Repo de entrega sin publicar**: sin remote en GitHub; cierre domingo 11:00. Acción: crear repo público, push, teamId en la descripción.
2. **P0 (abierto) — teamId no verificable**: pendiente manual junto con el push.
3. **PARCIAL (sin cambios) — 8 ADRs vs 2-5**: mitigado dentro del PDF (pág. 15).
4. **MENOR (sin cambios) — Códigos históricos** en ADR-05 / evidencia lote 1 (`video/data_outcomes_lote1_NOTA.md`).
5. **MENOR (sin cambios) — Costura ERP sin cliente HTTP** en `src/filemaid/` (los 3 CSV del lote 2 en disco [re-confirmado]).
6. **INFO — Vídeo re-renderizado sin commitear** (8 597 508 → 8 549 736 B, misma duración 180,000 s): no afecta a los 3 entregables de la raíz.
7. **INFO — gitignore de entregables** (§8.3): evitar `git add` de los entregables en el repo de solución; sincronizar al delivery-repo por copia.
8. **INFO — Trabajo de la ola en curso sin commitear** (watcher, UI, benchmarks, vídeo): ninguno toca entregables; el verificador debe re-auditar tras aterrizar los commits.

### 8.8 Estado de confianza (veredicto global)

**Los 3 entregables están en perfecto estado y son verificables byte a byte**: 540/540 filas JSONL válidas bajo el contrato exacto (`file_id` = basename del PDF, `result` en el dominio cerrado {PAGAR, NO_PAGAR, ESCALAR}), cobertura 1:1 contra los 540 PDFs de ambos lotes, 0 solapes, 0 duplicados, y hashes idénticos entre repo de solución y delivery-repo. La rúbrica (35/20/25/10/10 + bonus) se cumple con evidencia medida en todos los criterios; los únicos dos puntos que impiden declarar la entrega lista NO dependen del repo: **publicar el delivery-repo en GitHub y compartir el teamId**. Es la misma conclusión de las dos auditorías previas y sigue siendo el único camino bloqueante.

- **Confianza en los entregables (JSONL + PDF): ALTA** — triple verificación independiente (base, re-auditoría §7, esta §8) con resultados idénticos y hashes estables.
- **Confianza en la rúbrica: ALTA** — todos los criterios con evidencia medida; único riesgo no nulo: el conteo de 8 ADRs vs 2-5 (mitigado dentro del propio PDF).
- **Bloqueantes de entrega: 2 P0 operacionales** (push a GitHub + teamId). Sin acción del equipo antes del domingo 11:00, la entrega no puede ser validada por la organización aunque los ficheros son perfectos.
- **Estado del repo de solución: LIMPIO en cuanto a entregables**; la ola de trabajo en curso (watcher/UI/benchmarks/vídeo) refuerza los criterios de calidad/escalabilidad sin tocar los ficheros de entrega.

## 9. Re-auditoría 2026-09-20 (cuarta pasada, sobre `2159e0b` — ReauditorRequisitos)

**Alcance:** revalidación con medidas propias sobre el estado ACTUAL del repo tras aterrizar la ola de trabajo reportada como «en curso» en §8 (commits `a35bf3d` watcher E2E, `c295bed` tests, `c3d51cf` vídeo re-render, `188e6ef` benchmarks VLM local, `2159e0b` UI menos clics). Todas las medidas de esta sección son propias, ejecutadas en esta sesión con `uv run python`. La web https://hackathon.maisa.ai/ fue recargada íntegra (395 líneas): rúbrica sin cambios — 100 pts + 10 bonus (35/20/25/10/10), desempates escalabilidad → resiliencia → bonus, lote 2 sábado 18:00, cierre domingo 11:00, defensa 10 min (2+2+4+2), contrato JSONL `{"file_id":"...","result":"..."}` con `file_id` = nombre exacto del PDF.

### 9.1 Estado del árbol [medido]

- `git log -1` → `2159e0b` «UI: menos clics en el flujo frecuente…» (2026-09-20 04:54:45 +0000), rama `feat/remotion-polish`. `git status --short` → **vacío: working tree limpio**, sin cambios sin commitear (a diferencia de §8.1, la ola está completamente aterrizada).
- `git diff --stat 6bc93ac..HEAD` → 19 ficheros, +604/−82: watcher (`src/filemaid/desktop/watcher.py`, `tests/test_desktop_watcher.py`), benchmarks (`docs/benchmark_local_vs_remoto.md` nuevo, `docs/capacidad_y_coste.md`, `scripts/bench_vlm_local.py`, 2 JSON en `data/`), vídeo (`video/out/filemaid.mp4`, `video/README.md`, `video/src/`), UI (`frontend/src/App.vue`, `InvoiceDrawer.vue`, `nav.ts`, `api.ts`) y este doc. **Ningún cambio toca los 3 entregables de la raíz** (siguen en `.gitignore:33-41` por diseño; viven en el delivery-repo).
- Tests: **40 ficheros en `tests/`, 295 funciones `def test`** [medido con grep, sin cambios vs §8.1].
- Comprobación de zona ajena: la sección `outcomes.*` de `master/rules.yaml` (frontera NO_PAGAR/ESCALAR, ADR) no aparece en el diff `6bc93ac..HEAD` — intacta.

### 9.2 Validación de los 2 JSONL de la raíz (parseo programático propio) [medido]

Script `uv run python` (json.loads línea a línea + `os.listdir` de los PDFs en disco del repo de solución):

| Check | `outcomes.jsonl` | `outcomes_lote2.jsonl` |
|---|---|---|
| Líneas / JSON válido | 500/500 | 40/40 |
| Claves exactamente `{file_id, result}` (0 extra) | 500/500 | 40/40 |
| `file_id` basename exacto (sin `/` ni `\`) | 500/500 | 40/40 |
| `result ∈ {PAGAR, NO_PAGAR, ESCALAR}` | 500/500 | 40/40 |
| Únicos / duplicados | 500 / 0 | 40 / 0 |
| Cobertura vs PDFs en disco (missing/extra) | 0/0 (500 PDFs en `caja-de-alberto/facturas/`) | 0/0 (40 PDFs en `caja-de-alberto/facturas_primin/`) |
| Distribución | **PAGAR 433 / NO_PAGAR 22 / ESCALAR 45** | **PAGAR 26 / NO_PAGAR 11 / ESCALAR 3** |

Solapamiento lote1 ∩ lote2: **0**. Incidencias totales: **0**. Idéntico al resultado de las tres pasadas previas.

### 9.3 Entregables y hashes [medido]

```
$ sha256sum outcomes.jsonl outcomes_lote2.jsonl albertitos_plan.pdf          # raíz repo de solución
67a1acea40b48813c60753d1da6d7adeb9492acda3c2132491a095b1403a0eb7  outcomes.jsonl
34d55cb41c8bcece40e4e7c5e2fb75bf5c16b844d9ac766c215783e775d0fc4b  outcomes_lote2.jsonl
c64db1be58ea0d5d1939a325dcc3ee826712f7db4c7b7257a5d58b50d3466cc6  albertitos_plan.pdf
```

- Los 3 hashes son **idénticos** en la copia de entrega `/home/deploy/delivery-repo` [sha256sum en ambas copias, esta sesión]. `albertitos_plan.pdf` → 149 321 B, byte-idéntico a `docs/report/albertitos_plan.pdf` (mtimes 01:57:46 / 01:57:22, sin cambios desde §8).
- Delivery-repo: `ls -A` → raíz con **EXACTAMENTE** `albertitos_plan.pdf`, `outcomes.jsonl`, `outcomes_lote2.jsonl` + `.git/`; 4 commits (último `4fbb881`), working tree limpio; `git remote` → **0 líneas** (**P0 sigue abierto**, §9.7).

### 9.4 albertitos_plan.pdf — contenido [medido con pypdf]

- **15 páginas** [pypdf]. «Escalabilidad y coste» en págs. 2 y 6; **«Escalabilidad y coste» + «Resiliencia» juntas en la pág. 6**; menciones de ADR-01 en págs. 9, 13 y 15; **ADR-08 en pág. 14**; **mitigación del conteo de ADRs en la pág. 15**.
- **8 ADRs declarados** [grep -c '#adr(' docs/report/albertitos_plan.typ → 8], **0 placeholders** `PENDIENTE-MEDICIÓN` [grep → 0]. **Sigue PARCIAL por conteo** (web: «de 2 a 5 decisiones relevantes»), con la mitigación dentro del propio PDF.

### 9.5 Vídeo — CAMBIO confirmado y ahora commiteado [medido]

- `video/out/filemaid.mp4`: **8 603 731 bytes**, sha256 `1c8fcf371d7dfc579e6b489638722704865bbefce6683ac7c00e09c9a873e4d3` [stat + sha256sum]; átomo `mvhd` v0, timescale 1000, duration **180 000 → 180,000 s exactos** [parseo propio del átomo con `uv run python`, ffprobe no disponible en esta máquina].
- Contraste con `video/README.md` (commitado en `c3d51cf`): declara «180,000000 s exactos (5400 frames)», «**8 603 731 bytes (~8,2 MB)**» y «sha256 `1c8fcf371d7dfc57…`» — **los 3 valores coinciden exactamente con lo medido en disco**. README y binario están sincronizados.
- Estado git: el MP4 está **trackeado** (`git ls-files video/out` → solo `filemaid.mp4`), `git status --short video/` → vacío, y `git show c3d51cf --stat -- video/out` confirma el blob commiteado (Bin 8597508 → 8603731). Es decir: lo que §8.5 reportó como «re-render sin commitear (8 549 736 B)» fue sustituido por un re-render posterior (8 603 731 B) que **ya está commitado y limpio**. El tamaño de `video/out` en disco incluye aún stills de verificación sin trackear (ignorados por `9dc7f07`); no afecta.
- Drills [video/data_drills.json, medido]: 4/4 PASS (`rung5-provider-caido`, `backoff-429`, `crash-reanudacion`, `ledger-corrupto`).

### 9.6 Rúbrica — veredicto por criterio (evidencia de HOY)

| Criterio | Veredicto | Evidencia clave (esta sección) |
|---|---|---|
| Producto, arquitectura y ADRs (35) | ✅ CUMPLE con ⚠️ riesgo de conteo | §9.4: 15 págs, escalabilidad+resiliencia pág. 6, 8 ADRs mitigados en pág. 15 |
| Trazabilidad y observabilidad (20) | ✅ CUMPLE | §9.2: 8 reglas v3, señales `/api/salud\|jobs\|trazas\|reprocesar`; provenance lote 1 documentada (`video/data_outcomes_lote1_NOTA.md`) |
| Escalabilidad y coste (25) | ✅ CUMPLE (reforzado) | PDF pág. 6 + `docs/capacidad_y_coste.md` + **`docs/benchmark_local_vs_remoto.md` (170 líneas, commiteado en `188e6ef`) con medición limpia del VLM local en reposo (p50 3,9 s) y comparativa local vs remoto** — ahora el criterio tiene medición local propia, no solo cloud |
| Resiliencia y recuperación (10) | ✅ CUMPLE | Drills 4/4 PASS [§9.5]; retry `_MAX_ATTEMPTS=3` + Retry-After en `cloud_vlm.py` (sin commits que lo toquen desde `65f3ce4`) |
| Calidad de ejecución (10) | ✅ CUMPLE (reforzado) | 40 ficheros / 295 tests [§9.1]; **`uv run pytest tests/test_desktop_watcher.py` → 19 passed (11,43 s) [ejecutado por mí esta sesión]**: vigilancia E2E con hilo real + estado de sondeo (`poll_interval`, `last_scan`) |
| Bonus mejora adicional (+10) | ✅ CUMPLE | Watcher + notificación ESCALAR, implementada y mostrada en el vídeo commiteado de 180,000 s [§9.5]; **UI pulida en `2159e0b`: CTA a Revisión con badge de pendientes, atajo R, Enter/Esc en el drawer** — la mejora es más fácil de demostrar en la defensa |
| Contrato JSONL y cobertura | ✅ CUMPLE | 540/540 filas válidas, 0 incidencias, cobertura exacta 500+40, 0 solapes [§9.2] |
| Repo de entrega público + teamId | ❌ NO_CUMPLE | `git remote` → 0 líneas; teamId no verificable [§9.3] |

### 9.7 Hallazgos de esta pasada

1. **P0 (abierto) — Repo de entrega sin publicar**: `git remote` en `/home/deploy/delivery-repo` sigue devolviendo 0 líneas [medido]. Cierre domingo 11:00. Acción: crear repo público, push, teamId en la descripción.
2. **P0 (abierto) — teamId no verificable**: pendiente manual junto con el push.
3. **PARCIAL (sin cambios) — 8 ADRs vs 2-5**: mitigado dentro del PDF (pág. 15).
4. **MENOR (sin cambios) — Códigos históricos** en ADR-05 / evidencia lote 1 (`video/data_outcomes_lote1_NOTA.md`).
5. **MENOR (sin cambios) — Costura ERP sin cliente HTTP** en `src/filemaid/` (CSV del lote 2 en disco; no re-confirmado fichero a fichero en esta pasada).
6. **RESUELTO (era INFO en §8.7.6) — Vídeo sin commitear**: `c3d51cf` commita el re-render definitivo (8 603 731 B) con README verificado; los 3 valores del README (duración, bytes, sha256) coinciden con lo medido en disco [§9.5]. Working tree limpio.
7. **RESUELTO (era INFO en §8.7.8) — Ola de trabajo sin commitear**: los 5 commits de la ola (`a35bf3d`, `c295bed`, `c3d51cf`, `188e6ef`, `2159e0b`) están aterrizados y el árbol está limpio [§9.1]. Ninguno tocó los 3 entregables de la raíz.
8. **INFO (sin cambios) — gitignore de entregables** (§8.3): evitar `git add` de los entregables en el repo de solución; sincronizar al delivery-repo por copia.
9. **INFO — ffprobe ausente en esta sesión**: la duración del MP4 se midió por parseo propio del átomo `mvhd` (equivalente: duration/timescale = 180,000 s); la verificación ffprobe original consta en el mensaje de `c3d51cf`.

### 9.8 Estado de confianza (veredicto global)

**Los 3 entregables siguen en perfecto estado y la ola commiteada refuerza la rúbrica sin tocarlos.** Cuarta verificación independiente con resultado idéntico: 540/540 filas JSONL válidas bajo el contrato exacto, cobertura 1:1 contra los 540 PDFs, 0 solapes, 0 duplicados, y hashes estables entre repo de solución y delivery-repo (`67a1acea…`, `34d55cb4…`, `c64db1be…` en ambas copias). Los refuerzos nuevos de esta pasada son evidencia medida, no promesas: benchmarks locales vs remoto commiteados (p50 3,9 s en reposo), suite E2E del watcher ejecutada por el auditor (19 passed), vídeo commiteado con README verificado contra sha256 y bytes reales, y UI con badge de revisión que acorta la demo.

- **Confianza en los entregables (JSONL + PDF): ALTA** — cuádruple verificación independiente (base, §7, §8, esta §9) con resultados idénticos y hashes estables.
- **Confianza en la rúbrica: ALTA** — todos los criterios con evidencia medida; único riesgo no nulo: el conteo de 8 ADRs vs 2-5 (mitigado dentro del propio PDF, pág. 15).
- **Bloqueantes de entrega: los mismos 2 P0 operacionales** (push a GitHub + teamId). Ningún veredicto de rúbrica cambia respecto a §8, por lo que **la checklist de §6 sigue válida tal cual**: sus 2 primeros ítems (repo público + teamId) siguen siendo los únicos bloqueantes, y el ítem P2 («pág. 7» → «pág. 6») sigue aplicando para materiales de apoyo.
- **Estado del repo de solución: LIMPIO** — `git status --short` vacío sobre `2159e0b`; no queda trabajo en curso que re-auditar.
