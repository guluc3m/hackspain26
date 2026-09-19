# T20 · Guion de defensa + checklist de demo
assignee: W3
priority: p2

## Objetivo
`docs/report/DEFENSA.md` — el guion de los 10 minutos (hackathon.maisa.ai):
1. Demo y contexto (2 min): qué le ahorra a Alberto; UI en vivo con el lote
   real (Operaciones → Facturas → una factura PAGAR con su traza → Revisión
   con un escalado real → Reglas con el what-if).
2. Arquitectura y ADRs (2 min): la escalera por página con los números medidos
   (471/500 texto usable, 29 raster, rung 4 serializado 31 s/página), 5 ADRs
   (leer del PDF, no recitar).
3. Trazabilidad, escala y coste (4 min): seguir UNA decisión real end-to-end
   (file_id → ledger → evidencia por rung → reglas con provenance → resultado);
   files/s medido, fórmula de coste explícita (medido vs estimado), límites y
   cómo se añaden emails/imágenes/Excel (T18/T13: reglas y datos, sin motor).
4. Resiliencia (2 min): drills T12 (4/4 PASS: proveedor caído→ESCALAR, 429→
   backoff, crash→reanudación sin duplicados, ledger corrupto→tolerado);
   mostrado en la pantalla Salud.

## Reglas
- Cada número citado en el guion debe existir en .sdd/metrics/ con fuente.
- El guion NO inventa: si un dato falta, marca PENDIENTE.
- Incluye checklist operativo: comandos para levantar la demo (uvicorn, el
  store real, llama-server si aplica) y qué mostrar si algo falla en vivo
  (plan B: capturas del store real).

## Criterios de aceptación
- DEFENSA.md en docs/report/ con las 4 secciones y el checklist.
- Cada cifra citada tiene su fuente en un comentario al pie.
- pytest+ruff verde; ticket a closed en el mismo commit.
