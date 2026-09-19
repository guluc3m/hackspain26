# T33-M1 · PSM de tesseract como configuración (superficie de config)
assignee: W1
priority: p2

## Objetivo
Sacar el `--psm 6` hardcodeado del rung 3 (src/albertitos/extract/rungs.py:230)
a `ExtractionConfig.tesseract_psm` — los umbrales/parámetros de extracción son
CONFIGURACIÓN, no código (AGENTS.md §3/§4, doctrina del T10: «Thresholds are
configuration, not code»).

## Cambio
- `ExtractionConfig.tesseract_psm: int = 6` (comportamiento idéntico por
  defecto: 6 = «single uniform block», el usado en la calibración T10).
- `run_tesseract` usa `--psm {cfg.tesseract_psm}`.
- Cache: la clave de página incluye `config_version`; añadir un campo con
  default igual NO invalida el cache existente (comportamiento idéntico).

## Test
Con un binario tesseract FALSO (script que devuelve un TSV mínimo y registra
los args recibidos): el rung 3 pasa `--psm` con el valor de config y acepta
el texto; con `tesseract_psm=3` recibe `--psm 3`.