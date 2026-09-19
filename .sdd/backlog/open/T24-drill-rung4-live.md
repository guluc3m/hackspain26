# T24 · Drill en vivo: matar llama-server a mitad de una corrida real
assignee: W2
priority: p1

## Objetivo
Los drills T12 usan mocks. Este es REAL: demuestra la degradación con el VLM
local vivo y muerto, midiendo todo — es la evidencia de resiliencia que se
muestra en la defensa.

## Protocolo (store TEMPORAL, nunca el real)
1. Levanta (si no está) llama-server en 127.0.0.1:8080 (ya corriendo: health).
2. Corre `python -m albertitos.run --only "scan_0[12]*.pdf"` (los que van a
   rung 4) contra un store temporal con 20 archivos.
3. A mitad de la corrida: `pkill -f llama-server` (regístralo con timestamp).
4. Mide: los archivos en vuelo → qué hacen (timeout? retry? ESCALAR con
   motivo?), el resto del lote sigue por rung 1-3 sin tocar rung 4, y las
   páginas afectadas quedan ESCALAR/pendientes en cola de revisión.
5. Reinicia llama-server, re-corre: los pendientes se completan (resume
   idempotente) y el outcomes final es idéntico al de una corrida sin kill
   (byte a byte) — determinismo tras recuperación.
6. En paralelo: verifica que 3 workers + UI + ERP sigue en verde (la corrida
   NO puede matar a la flota: nice/cgroups si hace falta).

## Entregable
`.sdd/metrics/drill-rung4-live.json`: timeline (t=0 arranca, t=X kill, t=Y
detectado, t=Z colas afectadas, t=W recuperación completa), files/s antes y
después, y una nota para el guion de defensa (Salud screen lo muestra).

## Criterios de aceptación
- Test: el drill corre con un stub de llama-server que muere (sin red real);
  resultados idénticos con y sin kill.
- perfíl del sistema no degradado durante el drill (RAM bajo control).
- pytest+ruff verde; ticket a closed en el mismo commit.
