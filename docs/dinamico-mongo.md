# Mongo dinámico — por qué, qué y cómo

## Alcance (decisión KISS)

Mongo se usa SOLO donde el esquema es el problema: el **estado de facturas**
(documento flexible: campos fijos + subdocumento `extra` libre — un campo
nuevo por país/administración no exige migrar el esquema, solo crear un
índice si se quiere filtrar por él) y las **variables dinámicas filtrables**
(colección `attrs`, equivalente a `invoice_attrs` de SQLite).

SQLite se queda con lo estrictamente relacional: `evidence`,
`decision_runs` (histórico append-only), `stage_cache` y `resolutions`.
Migrarlo no aporta valor (acceso por clave, no flexible) y doblaría las
superficies de fallo.

**SQLite sigue siendo la fuente de autoridad.** Mongo es un espejo consultable:
si Mongo cae, no se pierde nada y la app sigue (AGENTS.md §5).

## Colecciones (db `albertitos`)

- `facturas`: un documento por factura — mismos campos fijos que la tabla
  `invoices` de SQLite (file_id, invoice_id, sha256, result, rule_codes,
  numero_factura, pedido, nif, iban, config_version, engine_version,
  updated_at, run_id) + `extra` como subdocumento libre.
  - Índice único: `file_id`.
  - Para filtrar por un campo nuevo (p. ej. `extra.moneda` en el ejemplo
    Perú) se crea el índice A DEMANDA: el índice es una decisión de
    consulta, no de esquema.
- `attrs`: clave-valor por factura (file_id, key, value). Índices:
  `(key, value)` y `file_id`.

## Cómo corre Alberto

1. Por defecto (sin `MONGO_URI`): todo en SQLite, como siempre. El fichero
   `<raíz-store>/store-backend.json` dice `{"backend": "sqlite", ...}` y
   `/salud` lo muestra.
2. Con `MONGO_URI=mongodb://...` en el entorno: al arrancar, el `Store`
   conecta (timeout 2 s, jamás lanza) y **espeja** cada
   `record_decision` a Mongo. El marker pasa a `{"backend": "mongo"}`;
   si Mongo deja de responder, `/salud` muestra el estado `down` y la app
   sigue funcionando con SQLite.
3. Migración de un store existente (idempotente, upsert por `file_id`):

   ```python
   from albertitos.store_mongo import connect_mongo, migrar_sqlite_a_mongo
   backend, estado = connect_mongo()          # respeta MONGO_URI
   n = migrar_sqlite_a_mongo(backend, ".sdd/store.db")
   ```

   Lo relacional (evidence, decision_runs, stage_cache, resolutions) se
   queda en SQLite por diseño.

## Dependencias

`pymongo` es OPCIONAL y se importa con pereza (sin servidor no hace falta):
si falta, `connect_mongo` devuelve estado `sin-pymongo` y la app sigue en
SQLite. No se añadió a las dependencias fijas.

## Ejemplo (Perú)

```python
store.record_decision(
    decision, sha, numero_factura="F001", pedido="P01", engine_version="v4",
    extra={"ruc": "20123456789", "moneda": "PEN", "monto_soles": 1250.5},
)
# en Mongo:
#   db.facturas.find({"extra.moneda": "PEN"})
#   db.attrs.find({"key": "moneda", "value": "PEN"})
```

Con SQLite el mismo filtro existe vía `invoice_attrs` (`files_with_attr`).
El motor de reglas sigue puro y determinista: Mongo es SOLO persistencia.
