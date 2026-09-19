# albertitos

Sistema de decisión para las facturas de Alberto: lee PDFs, extrae campos y decide
si cada factura se puede pagar — `PAGAR`, `NO_PAGAR` o `ESCALAR` — con evidencia
y trazabilidad en cada paso.

```
PDF ──▶ EXTRACCIÓN ──▶ FEATURES ──▶ PARSER ──▶ CAMPOS ──▶ MOTOR DE REGLAS ──▶ RESULTADO
                                                               │
                                                     evidencia + config ──▶ STORE ──▶ UI
```
