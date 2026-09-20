# Auditoría de requisitos — Maisa «500 Sombras de Alberto»

**Proyecto:** filemaid · **Repo:** `/home/deploy/hackspain26` · **Rama:** `feat/remotion-polish` · **Commit auditado:** `19aebd8` (HEAD; re-auditoría VerifAuditoria sobre `19aebd8` confirma las medidas: los 3 commits posteriores a `7ace882` no tocan entregables)
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

*Auditoría ejecutada el 2026-09-20 sobre `7ace882` por AuditorReq. Medidas propias de esta sesión: parseo programático de ambos JSONL (540/540 líneas válidas, 0 incidencias), cobertura exacta contra los directorios de PDFs, pypdf sobre `albertitos_plan.pdf` (15 págs, escalabilidad pág. 6, ADRs págs. 10–15, mitigación pág. 15), grep de ADRs y placeholders en `albertitos_plan.typ` (8 ADRs, 0 placeholders), lectura de ADR-05, verificación de `/home/deploy/delivery-repo` (raíz exacta, hashes, sin remote), lectura íntegra de `video/data_outcomes_lote1_NOTA.md`, parseo `mvhd` del vídeo (180,000 s, 8 597 508 bytes) y contraste de la rúbrica contra https://hackathon.maisa.ai/ (cargada completa). No se ejecutaron suites completas, formateadores ni lint (restricción de la asignación).*
