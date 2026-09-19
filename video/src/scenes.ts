// Escenas del vídeo filemaid — 3 min, 30 fps, 1920×1080.
// Datos reales del repo (ver GUION.md).

export const FPS = 30;
export const WIDTH = 1920;
export const HEIGHT = 1080;

export type Scene = {
  id: string;
  frames: number;
};

export const SCENES: Scene[] = [
  { id: 'portada', frames: 360 },
  { id: 'problema', frames: 690 },
  { id: 'producto', frames: 600 },
  { id: 'escalera', frames: 900 },
  { id: 'traza', frames: 1050 },
  { id: 'adrs', frames: 600 },
  { id: 'resiliencia', frames: 600 },
  { id: 'escala', frames: 600 },
];

export const TOTAL_FRAMES = SCENES.reduce((acc, s) => acc + s.frames, 0);
if (TOTAL_FRAMES !== 5400) {
  throw new Error(`El vídeo debe durar 3 min (5400 frames), hay ${TOTAL_FRAMES}`);
}

// Paleta exacta de frontend/src/style.css (tokens de docs/report/lib.typ)
export const C = {
  paper: '#f4ecd8',
  ink: '#2a170f',
  brown: '#4a2c1f',
  gold: '#eab619',
  orange: '#d96b2a',
  red: '#cc291f',
  slate: '#8fb8d1',
  teal: '#35858a',
  sand: '#e8dcc4',
  panel: '#faf4e6',
  borderSoft: '#c9bda2',
  okBg: '#dceceb',
  badBg: '#f6dcd8',
  warnBg: '#f7e3d3',
} as const;

// Métricas medidas (data_lote1.json / data_dryrun.json / data_drills.json)
export const METRICS = {
  nArchivos: 500,
  pagares: 433,
  noPagares: 22,
  escalares: 45,
  filesPerS: 4.162,
  latenciaTotalS: 120.1,
  costeCloudEur: 0.0,
  textoUsable: 471,
  textoUsablePct: 94.2,
  raster: 29,
  rung1FilesPerS: 2636,
  rung1MeanMs: 0.4,
  rung2MeanMs: 42.1,
  vlmLocalMeanMs: 33870,
  vlmCloudMeanMs: 1555,
} as const;

// Escalera de extracción (docs/report/architecture.typ)
export const ESCALERA = [
  { n: 1, tech: 'Texto vectorial', sub: 'pypdf · filtro anti-mojibake', cost: '0 €', speed: '< 1 ms', pct: 94.2 },
  { n: 2, tech: 'Rasterizado + QR', sub: 'pypdfium2 + zxing · 300 DPI', cost: '0 €', speed: '~40 ms', pct: 5.8 },
  { n: 3, tech: 'Tesseract OCR', sub: 'doble puerta: word-conf + cobertura', cost: '0 €', speed: '~150 ms' },
  { n: 4, tech: 'VLM local', sub: 'PaddleOCR-VL 1.6 Q8 · llama-server', cost: '0 €', speed: '~1,7 s' },
  { n: 5, tech: 'TypeSafe System One', sub: 'decisiones tipadas paralelas', cost: '~0,04 $/Mtok', speed: '~560 ms' },
  { n: 6, tech: 'Firecrawl parse', sub: 'rescate de tablas complejas', cost: '1 credit', speed: '~1,2 s' },
  { n: 7, tech: 'Cloud VLM >25B', sub: 'último recurso · candidato, nunca respuesta', cost: 'pago token', speed: '~3 s' },
] as const;

export const DRILLS = [
  { name: 'rung5-provider-caido', detail: 'proveedor caído → cola de revisión, el lote sigue' },
  { name: 'backoff-429', detail: 'Retry-After respetado, 0 llamadas extra' },
  { name: 'crash-reanudacion', detail: 'crash al índice 2 → reanuda, 0 duplicados' },
  { name: 'ledger-corrupto', detail: 'ledger dañado → store consistente' },
] as const;

export const REGLAS = [
  'NIF_IN_MASTER', 'IBAN_MATCHES_MASTER', 'ORDER_BELONGS_TO_SUPPLIER',
  'ORDER_AMOUNT_MATCHES', 'TOTALS_MUST_MATCH', 'IVA_CONSISTENT',
  'DATE_VALID_NOT_FUTURE', 'ORDER_PENDING', 'NO_DOUBLE_PAYMENT',
  'NO_EMBEDDED_INSTRUCTIONS', 'PROVEEDOR_FANTASMA', 'AMOUNT_OUTLIER',
] as const;

// Casos reales de data_outcomes_lote1.jsonl
export const CASO_DUPLICADO = {
  file_id: 'factura_8801.pdf',
  result: 'NO_PAGAR',
  fails: ['ORDER_AMOUNT_MATCHES:FAIL', 'NO_DOUBLE_PAYMENT:FAIL'],
  nota: '2ª copia del duplicado FA-8801: no paga',
} as const;

export const CASO_SCAN = {
  file_id: 'scan_001.pdf',
  result: 'ESCALAR',
  unknowns: 11,
  nota: 'escaneo ilegible: 11 reglas UNKNOWN ⇒ duda razonable',
} as const;

export const CASO_ESCALAR = {
  file_id: '2026-03-19_P008.pdf',
  result: 'ESCALAR',
  unknowns: ['DATE_VALID_NOT_FUTURE:UNKNOWN'],
  nota: 'fecha ilegible en evidencia ⇒ ESCALAR, no PAGAR',
} as const;
