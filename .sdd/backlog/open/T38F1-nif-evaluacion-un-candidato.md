# T38-F1 · NIF_IN_MASTER colapsa con el 1er candidato (misma clase que el ROJO del T17)
assignee: supervisor (semántica de motor = ADR)
priority: p1
severidad: p1

## Hallazgo
`_r_nif` (src/albertitos/rules/engine.py) usa `_pick` (1er candidato / max
confianza) en vez de evaluar TODOS los candidatos como exige ADR-06 para los
campos comparados contra el maestro. Un NIF etiquetado que NO está en el
maestro + un segundo candidato SÍ válido ⇒ FAIL definitivo ⇒ NO_PAGAR falso,
la misma clase de bug que el T17 midió para importes (87/108 falsos).

## Reproducción (pasos exactos, verificado hoy)
Texto con NIF etiquetado inexistente + referencia interna que SÍ es un NIF del
maestro (fixture maestro_fixture.xlsx, proveedor P001 = B46102331):
```
PAPELERÍA RUZAFA S.C.
NIF: J99999999
Referencia interna: B46102331
IBAN: ES55 3159 0012 3487 6512 3407
Factura: FA-1480
Fecha factura: 26/01/2026    PO: PO-2026-0222
Subtotal: EUR 1409.40
IVA (21%): EUR 295.97
TOTAL A PAGAR: EUR 1705.37
```
`decide(...)` ⇒ `NIF_IN_MASTER: FAIL` con consumed.elegido="J99999999", cuando
"B46102331" (2º candidato) SÍ está en `master.proveedores_por_nif`. El resultado
del lote real depende de esto: cualquier factura con un NIF suelto válido
delante del etiquetado produce NO_PAGAR falso.

## Severidad
p1 — falso NO_PAGAR (violación definitiva) por selección de candidato, no por
datos. Fix propuesto (para ADR): extender ADR-06 a los cruces de match exacto
(NIF/fecha/numero_factura): si algún candidato matchea ⇒ PASS con provenance;
ninguno ⇒ FAIL. NO implementar sin supervisor (cambia resultados).

## Evaluación (W4, T39 — 2026-09-19): DE ACUERDO, ADR del supervisor requerido
El repro es correcto (verificado el mecanismo: `_r_nif` usa `_pick` = 1er
candidato por confianza, no `_match_all` como los cruces ADR-06). NO se
implementa desde el loop: cambia resultados del lote (falsos NO_PAGAR en la
clase de la misma familia que T17). W3 ya dejó tests xfail del repro en su
rama. Punto de atención para el ADR: la inyección de overrides humanos
(T38-F6, ya implementada) usa conf 1.0 y por tanto GANA el `_pick` — si el
ADR extiende `_match_all` a NIF/fecha/numero_factura, verificar que el
candidato humano siga pesando en los matches (debe: conf 1.0).
