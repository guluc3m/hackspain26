// Referencia sintética de la base de datos (sqlite) del backend.
//
// Modela las tablas que la UI consume: facturas, decisiones (cada una con su
// ID asignado), campos con todos los candidatos, evaluaciones de reglas por
// decisión, overrides y un log de entradas MÍNIMAS (solo tipo + IDs + ts):
// las reglas y el resto del detalle viven en las tablas, nunca en la entrada
// del log. Todo lo que muestra la UI se resuelve contra estas tablas.
//
// Estado mutable en memoria: override/reprocesar registran nuevos registros
// (la nueva decisión recibe su propio ID), sin invocar ningún motor.

import type {
  Candidate,
  FacturaRow,
  IngestResponse,
  InvoiceDetail,
  JobStatus,
  JobSummary,
  LogItem,
  LogType,
  LogsResponse,
  Reglas,
  Resolution,
  ResolveInput,
  ResolveResponse,
  Resultado,
  ReviewItem,
  ReviewState,
  RuleEvaluationRow,
  RuntimeConfig,
  RuntimeConfigInput,
  Salud,
  SyncStatus,
  VlmStatus
} from '../api'

const AHORA = () => Date.now() / 1000

function hex(n: number, seed: number): string {
  let out = ''
  let x = seed & 0x7fffffff
  while (out.length < n) {
    x = (x * 1103515245 + 12345) & 0x7fffffff
    out += x.toString(16).padStart(8, '0')
  }
  return out.slice(0, n)
}

function seedDe(texto: string): number {
  let s = 7
  for (let i = 0; i < texto.length; i++) s = (s * 31 + texto.charCodeAt(i)) & 0x7fffffff
  return s
}

function cand(extractor: string, value: Candidate['value'], confidence: number): Candidate {
  return { extractor, value, confidence }
}

// ---- tablas --------------------------------------------------------------

interface Factura {
  id: string
  file_id: string
  sha256: string
  first_seen: number
  last_seen: number
  status: string
  source_path: string
}

interface Decision {
  decision_id: string
  invoice_id: string
  result: Resultado
  timestamp: number
}

interface Evaluacion {
  decision_id: string
  code: string
  verdict: 'PASS' | 'FAIL' | 'UNKNOWN'
  reason: string
  timestamp: number
}

interface Override {
  id: number
  invoice_id: string
  field_type: string
  before: string // JSON en texto
  after: string
  who: string
  rung: string
  reason: string
  timestamp: number
}

/** Entrada del log: referencia mínima + payload estructurado. */
interface Evento {
  seq: number
  ts: number
  type: LogType
  invoice_id: string
  decision_id?: string
  override_id?: number
  payload?: Record<string, unknown>
}

const REGLAS: Reglas = {
  rule_set_version: 'v1',
  config_version: 'rules',
  enabled: [
    'DATE_VALID_NOT_FUTURE',
    'IBAN_MATCHES_MASTER',
    'IVA_CONSISTENT',
    'NIF_IN_MASTER',
    'NO_DOUBLE_PAYMENT',
    'ORDER_BELONGS_TO_SUPPLIER',
    'ORDER_PENDING',
    'TOTALS_MUST_MATCH'
  ],
  thresholds: {
    DATE_VALID_NOT_FUTURE: { min_confidence: 0.6 },
    IBAN_MATCHES_MASTER: { min_confidence: 0.7 },
    IVA_CONSISTENT: { min_confidence: 0.6 },
    NIF_IN_MASTER: { min_confidence: 0.7 },
    NO_DOUBLE_PAYMENT: { min_confidence: 0.7 },
    ORDER_BELONGS_TO_SUPPLIER: { min_confidence: 0.7 },
    ORDER_PENDING: { min_confidence: 0.7 },
    TOTALS_MUST_MATCH: { min_confidence: 0.7 }
  }
}

const SALUD: Salud = {
  tesseract: 'ok',
  'llama-server': 'ok',
  cloud_vlm: 'sin-clave',
  store: 'ok'
}

const CARPETA = '/data/lotes/caja-de-alberto'
const T0 = AHORA() - 3600

// ---- siembra --------------------------------------------------------------

interface Semilla {
  invoice: Factura
  campos: Record<string, Candidate[]>
  decisiones: { result: Resultado; haceSeg: number }[]
  evaluaciones?: { code: string; verdict: 'PASS' | 'FAIL' | 'UNKNOWN'; reason: string }[]
  overrides?: {
    field_type: string
    before: unknown
    after: unknown
    who: string
    rung: string
    reason: string
    haceSeg: number
  }[]
}

const VEREDICTOS_OK = [
  { code: 'DATE_VALID_NOT_FUTURE', verdict: 'PASS', reason: 'fecha válida y no futura' },
  { code: 'IBAN_MATCHES_MASTER', verdict: 'PASS', reason: 'IBAN coincide con el maestro' },
  { code: 'IVA_CONSISTENT', verdict: 'PASS', reason: 'base + IVA = total (tolerancia 0.01)' },
  { code: 'NIF_IN_MASTER', verdict: 'PASS', reason: 'NIF presente en el maestro' },
  { code: 'NO_DOUBLE_PAYMENT', verdict: 'PASS', reason: 'sin pago previo del pedido' },
  { code: 'ORDER_BELONGS_TO_SUPPLIER', verdict: 'PASS', reason: 'el pedido pertenece al proveedor' },
  { code: 'ORDER_PENDING', verdict: 'PASS', reason: 'estado ERP del pedido: PENDIENTE' },
  { code: 'TOTALS_MUST_MATCH', verdict: 'PASS', reason: 'importe igual al pedido (tolerancia 0.01)' }
] as const

const SEMILLAS: Semilla[] = [
  {
    invoice: {
      id: '5f0c3a2e-9b14-4c8d-a1e2-0a1b2c3d4e01',
      file_id: '2026-01-08_P001.pdf',
      sha256: hex(64, seedDe('2026-01-08_P001.pdf')),
      first_seen: T0,
      last_seen: T0 + 60,
      status: 'PAGAR',
      source_path: `${CARPETA}/2026-01-08_P001.pdf`
    },
    campos: {
      nif: [cand('regex', 'B12345678', 0.95), cand('tesseract', 'B12345678', 0.88)],
      iban: [cand('regex', 'ES9121000418450200051332', 0.97), cand('tesseract', 'ES9121000418450200051332', 0.9)],
      total: [cand('regex', 121.0, 0.98), cand('tesseract', 121.0, 0.91)],
      iva_amount: [cand('regex', 21.0, 0.9)],
      fecha: [cand('regex', '2026-01-08', 0.93)],
      pedido: [cand('regex', 'P-2026-001', 0.94)]
    },
    decisiones: [{ result: 'PAGAR', haceSeg: 590 }],
    evaluaciones: [...VEREDICTOS_OK]
  },
  {
    invoice: {
      id: '5f0c3a2e-9b14-4c8d-a1e2-0a1b2c3d4e02',
      file_id: '2026-01-11_P007.pdf',
      sha256: hex(64, seedDe('2026-01-11_P007.pdf')),
      first_seen: T0,
      last_seen: T0 + 60,
      status: 'NO_PAGAR',
      source_path: `${CARPETA}/2026-01-11_P007.pdf`
    },
    campos: {
      nif: [cand('regex', 'B87654321', 0.93)],
      iban: [cand('regex', 'ES7921000813610123456789', 0.95)],
      total: [cand('regex', 847.0, 0.96), cand('tesseract', 874.0, 0.62)],
      iva_amount: [cand('regex', 66.5, 0.87)],
      fecha: [cand('regex', '2026-01-11', 0.9)],
      pedido: [cand('regex', 'P-2026-002', 0.91)]
    },
    decisiones: [{ result: 'NO_PAGAR', haceSeg: 550 }],
    evaluaciones: [
      ...VEREDICTOS_OK.slice(0, 7),
      { code: 'TOTALS_MUST_MATCH', verdict: 'FAIL', reason: 'importe 847.00 difiere del pedido 121.00 (> 0.01)' }
    ]
  },
  {
    invoice: {
      id: '5f0c3a2e-9b14-4c8d-a1e2-0a1b2c3d4e03',
      file_id: '2026-01-12_P002.pdf',
      sha256: hex(64, seedDe('2026-01-12_P002.pdf')),
      first_seen: T0,
      last_seen: T0 + 60,
      status: 'ESCALAR',
      source_path: `${CARPETA}/2026-01-12_P002.pdf`
    },
    campos: {
      nif: [cand('regex', 'X1234567R', 0.9), cand('tesseract', 'X1234567R', 0.84)],
      iban: [cand('regex', 'ES1000492352082414205416', 0.91), cand('tesseract', 'ES1O00492352082414205416', 0.54)],
      total: [cand('regex', 60.5, 0.93), cand('vlm', 65.0, 0.71)],
      iva_amount: [cand('regex', 4.5, 0.79)],
      fecha: [cand('regex', '2026-01-12', 0.86)],
      pedido: [cand('tesseract', 'P-2026-003', 0.58), cand('vlm', 'P-2026-008', 0.61)]
    },
    decisiones: [
      { result: 'ESCALAR', haceSeg: 510 },
      { result: 'ESCALAR', haceSeg: 460 }
    ],
    evaluaciones: [
      { code: 'DATE_VALID_NOT_FUTURE', verdict: 'PASS', reason: 'fecha 2026-01-12 válida y no futura' },
      { code: 'IBAN_MATCHES_MASTER', verdict: 'PASS', reason: 'IBAN coincide con el maestro de X1234567R' },
      { code: 'IVA_CONSISTENT', verdict: 'UNKNOWN', reason: 'sin base extraída: no se puede verificar base + IVA' },
      { code: 'NIF_IN_MASTER', verdict: 'PASS', reason: 'X1234567R presente en el maestro' },
      { code: 'NO_DOUBLE_PAYMENT', verdict: 'UNKNOWN', reason: 'pedido ambiguo: P-2026-003 vs P-2026-008' },
      { code: 'ORDER_BELONGS_TO_SUPPLIER', verdict: 'UNKNOWN', reason: 'pedido ambiguo: no se cruza con el ERP con confianza' },
      { code: 'ORDER_PENDING', verdict: 'UNKNOWN', reason: 'pedido ambiguo: estado ERP no consultable' },
      { code: 'TOTALS_MUST_MATCH', verdict: 'PASS', reason: 'importe igual al pedido P-2026-003 (60.50, tolerancia 0.01)' }
    ],
    overrides: [
      {
        field_type: 'total',
        before: 65.0,
        after: 60.5,
        who: 'revisor',
        rung: 'review-ui',
        reason: 'corrección manual en revisión',
        haceSeg: 480
      }
    ]
  },
  {
    invoice: {
      id: '5f0c3a2e-9b14-4c8d-a1e2-0a1b2c3d4e04',
      file_id: '2026-01-23_P006.pdf',
      sha256: hex(64, seedDe('2026-01-23_P006.pdf')),
      first_seen: T0,
      last_seen: T0 + 60,
      status: 'PAGAR',
      source_path: `${CARPETA}/2026-01-23_P006.pdf`
    },
    campos: {
      nif: [cand('regex', 'B12345678', 0.94)],
      iban: [cand('regex', 'ES9121000418450200051332', 0.92)],
      total: [cand('regex', 242.0, 0.95)],
      iva_amount: [cand('regex', 42.0, 0.81)],
      fecha: [cand('regex', '2026-01-23', 0.89)],
      pedido: [cand('regex', 'P-2026-004', 0.83)]
    },
    decisiones: [{ result: 'PAGAR', haceSeg: 420 }],
    evaluaciones: [...VEREDICTOS_OK]
  },
  {
    invoice: {
      id: '5f0c3a2e-9b14-4c8d-a1e2-0a1b2c3d4e05',
      file_id: '2026-01-17_P011.pdf',
      sha256: hex(64, seedDe('2026-01-17_P011.pdf')),
      first_seen: AHORA() - 310,
      last_seen: AHORA() - 300,
      status: 'pendiente',
      source_path: `${CARPETA}/2026-01-17_P011.pdf`
    },
    campos: {},
    decisiones: []
  },
  {
    invoice: {
      id: '5f0c3a2e-9b14-4c8d-a1e2-0a1b2c3d4e06',
      file_id: 'inventario_enero.xlsx',
      sha256: hex(64, seedDe('inventario_enero.xlsx')),
      first_seen: T0,
      last_seen: T0 + 30,
      status: 'pendiente',
      source_path: `${CARPETA}/excel/inventario_enero.xlsx`
    },
    campos: {},
    decisiones: []
  },
  {
    invoice: {
      id: '5f0c3a2e-9b14-4c8d-a1e2-0a1b2c3d4e07',
      file_id: 'facturas_proveedores.xlsx',
      sha256: hex(64, seedDe('facturas_proveedores.xlsx')),
      first_seen: T0,
      last_seen: T0 + 30,
      status: 'pendiente',
      source_path: `${CARPETA}/excel/facturas_proveedores.xlsx`
    },
    campos: {},
    decisiones: []
  }
]

// ---- tablas en memoria ----------------------------------------------------

const facturas = new Map<string, Factura>()
const camposTabla = new Map<string, Candidate[]>() // clave: "<invoice_id>|<field_type>"
const decisiones: Decision[] = []
const evaluaciones: Evaluacion[] = []
const overrides: Override[] = []
const eventos: Evento[] = []
const revisiones = new Map<string, { state: ReviewState; resolution_id: string | null; resolution: Resolution | null }>()

function log(
  type: LogType,
  invoiceId: string,
  refs: { decision_id?: string; override_id?: number; payload?: Record<string, unknown> } = {},
  ts: number = AHORA()
): void {
  eventos.push({ seq: eventos.length + 1, ts, type, invoice_id: invoiceId, ...refs })
}

for (const s of SEMILLAS) {
  facturas.set(s.invoice.id, { ...s.invoice })
  for (const [fieldType, cs] of Object.entries(s.campos)) {
    camposTabla.set(`${s.invoice.id}|${fieldType}`, cs)
  }
}

function registrarDecision(invoiceId: string, fileId: string, result: Resultado, haceSeg: number, evals?: Semilla['evaluaciones']): Decision {
  const decision: Decision = {
    decision_id: `d-${hex(8, seedDe(fileId) + decisiones.length * 7919 + 11)}`,
    invoice_id: invoiceId,
    result,
    timestamp: AHORA() - haceSeg
  }
  decisiones.push(decision)
  for (const e of evals ?? []) {
    evaluaciones.push({
      decision_id: decision.decision_id,
      code: e.code,
      verdict: e.verdict,
      reason: e.reason,
      timestamp: decision.timestamp
    })
  }
  return decision
}

const decisionesPorSemilla = new Map<Semilla, Decision[]>()

for (const s of SEMILLAS) {
  decisionesPorSemilla.set(
    s,
    s.decisiones.map((d) =>
      registrarDecision(s.invoice.id, s.invoice.file_id, d.result, d.haceSeg, s.evaluaciones)
    )
  )
  ;(s.overrides ?? []).forEach((o) => {
    overrides.push({
      id: overrides.length + 1,
      invoice_id: s.invoice.id,
      field_type: o.field_type,
      before: JSON.stringify(o.before),
      after: JSON.stringify(o.after),
      who: o.who,
      rung: o.rung,
      reason: o.reason,
      timestamp: AHORA() - o.haceSeg
    })
  })
}

// log inicial (cronológico): una entrada mínima por transición registrada,
// con el ts del propio registro (decisión/override) que referencia
for (const s of SEMILLAS) {
  const creadas = decisionesPorSemilla.get(s) ?? []
  if (creadas.length === 0) {
    if (s.invoice.file_id.endsWith('.pdf')) {
      log('invoice_seen', s.invoice.id, {}, s.invoice.last_seen) // vista, aún sin decisión
    }
    continue
  }
  for (const dec of creadas) {
    log('invoice_seen', s.invoice.id, {}, dec.timestamp - 10)
    log('decision', s.invoice.id, { decision_id: dec.decision_id }, dec.timestamp)
  }
  for (const o of s.overrides ?? []) {
    const ov = overrides.find((x) => x.invoice_id === s.invoice.id && x.field_type === o.field_type)
    if (ov) log('override', s.invoice.id, { override_id: ov.id }, ov.timestamp)
  }
}
// seq = posición cronológica en el log
eventos.sort((a, b) => a.ts - b.ts)
eventos.forEach((e, i) => {
  e.seq = i + 1
})

// ---- consultas (como las leería el backend de la base de datos) ------------

function decisionesDe(invoiceId: string): Decision[] {
  return decisiones.filter((d) => d.invoice_id === invoiceId)
}

function ultimaDecision(invoiceId: string): Decision | null {
  const ds = decisionesDe(invoiceId)
  return ds.length === 0 ? null : ds[ds.length - 1]
}

/** Estado de revisión: solo las decisiones ESCALAR requieren revisión humana. */
function reviewDe(invoiceId: string): { state: ReviewState; resolution_id: string | null; resolution: Resolution | null } {
  const ult = ultimaDecision(invoiceId)
  if (!ult || ult.result !== 'ESCALAR') {
    return { state: 'not_required', resolution_id: null, resolution: null }
  }
  return revisiones.get(invoiceId) ?? { state: 'pending', resolution_id: null, resolution: null }
}

function aFila(f: Factura): FacturaRow {
  const ult = ultimaDecision(f.id)
  const cs = [...camposTabla.entries()].filter(([k]) => k.startsWith(`${f.id}|`))
  const rev = reviewDe(f.id)
  const disputed = ult?.result === 'ESCALAR' && rev.state === 'pending'
  return {
    id: f.id,
    file_id: f.file_id,
    status: f.status,
    source_path: f.source_path,
    folder: f.source_path.split('/').slice(0, -1).join('/'),
    result: ult?.result ?? null,
    decision_id: ult?.decision_id ?? null,
    decided_at: ult?.timestamp ?? null,
    iterations: decisionesDe(f.id).length,
    confidence:
      cs.length === 0
        ? null
        : Math.min(...cs.map(([, candidates]) => Math.max(...candidates.map((c) => c.confidence)))),
    disputed,
    withheld_from_sync: disputed,
    review_state: rev.state,
    resolution_id: rev.resolution_id
  }
}

function detalleDe(id: string): InvoiceDetail {
  const f = facturas.get(id)
  if (!f) throw new Error(`factura ${id} no encontrada`)
  const ult = ultimaDecision(id)
  const rev = reviewDe(id)
  const disputed = ult?.result === 'ESCALAR' && rev.state === 'pending'
  const fields: Record<string, Candidate[]> = {}
  for (const [k, cs] of camposTabla.entries()) {
    if (k.startsWith(`${id}|`)) fields[k.split('|')[1]] = cs
  }
  return {
    invoice: { ...f },
    fields,
    decision: ult ? { ...ult } : null,
    rule_evaluations: ult
      ? evaluaciones
          .filter((e) => e.decision_id === ult.decision_id)
          .map<RuleEvaluationRow>((e) => ({
            code: e.code,
            verdict: e.verdict,
            reason: e.reason,
            consumed: { fuente: 'sintético' },
            timestamp: e.timestamp
          }))
      : [],
    overrides: overrides.filter((o) => o.invoice_id === id).map((o) => ({ ...o })),
    disputed,
    withheld_from_sync: disputed,
    review_state: rev.state,
    resolution_id: rev.resolution_id,
    resolution: rev.resolution
  }
}

function reprocesar(fileId: string): { file_id: string; result: Resultado } {
  const f = [...facturas.values()].find((x) => x.file_id === fileId)
  if (!f) throw new Error(`factura ${fileId} no encontrada`)
  const esPdf = fileId.toLowerCase().endsWith('.pdf')
  const seed = SEMILLAS.find((s) => s.invoice.id === f.id)
  const pendiente = ultimaDecision(f.id) === null

  if (pendiente) {
    // primera decisión de referencia: el PDF trae sus campos sembrados
    for (const [fieldType, cs] of Object.entries(seed?.campos ?? {})) {
      camposTabla.set(`${f.id}|${fieldType}`, cs)
    }
  }

  // resultado sintético de referencia: PDF nuevo -> PAGAR; no-PDF -> ESCALAR
  const result: Resultado = pendiente ? (esPdf ? 'PAGAR' : 'ESCALAR') : ultimaDecision(f.id)!.result
  const evals = pendiente
    ? esPdf
      ? (seed?.evaluaciones ?? [...VEREDICTOS_OK])
      : undefined // sin evaluaciones ⇒ ESCALAR
    : seed?.evaluaciones

  const dec = registrarDecision(f.id, fileId, result, 0, evals)
  f.last_seen = AHORA()
  f.status = result
  log('invoice_seen', f.id)
  log('decision', f.id, { decision_id: dec.decision_id })
  return { file_id: fileId, result }
}

/** Resolución humana: overrides con procedencia y recálculo determinista. */
function resolver(invoiceId: string, body: ResolveInput): ResolveResponse {
  const f = facturas.get(invoiceId)
  if (!f) throw new Error(`factura ${invoiceId} no encontrada`)
  const ult = ultimaDecision(invoiceId)
  if (!ult) throw new Error('la factura no tiene decisión que resolver')
  if (body.expected_decision_id && body.expected_decision_id !== ult.decision_id) {
    throw new Error('la decisión cambió desde que se cargó: recargue antes de resolver')
  }

  const registrar = (fieldType: string, before: unknown, after: unknown) => {
    const id = overrides.length + 1
    overrides.push({
      id,
      invoice_id: invoiceId,
      field_type: fieldType,
      before: JSON.stringify(before),
      after: JSON.stringify(after),
      who: body.who,
      rung: 'review-ui',
      reason: body.reason,
      timestamp: AHORA()
    })
    log('override', invoiceId, { override_id: id })
  }

  for (const fieldType of body.accepted) {
    const cs = camposTabla.get(`${invoiceId}|${fieldType}`) ?? []
    if (cs.length === 0) continue
    const lider = cs.reduce((b, c, i) => (c.confidence > cs[b].confidence ? i : b), 0)
    registrar(fieldType, cs[lider].value, cs[lider].value)
  }
  for (const [fieldType, value] of Object.entries(body.corrected)) {
    const cs = camposTabla.get(`${invoiceId}|${fieldType}`) ?? []
    const lider = cs.length ? cs.reduce((b, c, i) => (c.confidence > cs[b].confidence ? i : b), 0) : -1
    registrar(fieldType, lider >= 0 ? cs[lider].value : null, value)
  }

  // El motor recalcula de forma determinista; el resultado puede seguir ESCALAR.
  const dec = registrarDecision(invoiceId, f.file_id, ult.result, 0, undefined)
  const resolution: Resolution = {
    who: body.who,
    reason: body.reason,
    accepted: body.accepted,
    corrected: Object.fromEntries(Object.entries(body.corrected).map(([k, v]) => [k, String(v)])),
    timestamp: AHORA()
  }
  const resolution_id = `res-${hex(8, seedDe(f.file_id) + revisiones.size * 7919 + 17)}`
  revisiones.set(invoiceId, { state: 'resolved', resolution_id, resolution })
  f.status = dec.result
  log('decision', invoiceId, { decision_id: dec.decision_id })
  return {
    ok: true,
    resolution_id,
    decision_id: dec.decision_id,
    result: dec.result,
    review_state: 'resolved',
    disputed: false
  }
}

/** Cola de revisión: solo las decisiones ESCALAR pendientes. */
function revisionList(): { items: ReviewItem[] } {
  const items: ReviewItem[] = []
  for (const f of facturas.values()) {
    const ult = ultimaDecision(f.id)
    if (!ult || ult.result !== 'ESCALAR') continue
    const rev = reviewDe(f.id)
    if (rev.state !== 'pending') continue
    items.push({
      file_key: f.id,
      file_id: f.file_id,
      result: ult.result,
      decision_id: ult.decision_id,
      scan_id: f.id,
      review_state: rev.state,
      reason: 'decisión escalada: requiere revisión humana',
      since: ult.timestamp
    })
  }
  return { items }
}

/** Resumen semántico + payload estructurado, resueltos contra las tablas. */
function summaryDe(e: Evento): { summary: string; payload: Record<string, unknown> } {
  switch (e.type) {
    case 'invoice_seen':
      return {
        summary: 'factura registrada',
        payload: { file_id: facturas.get(e.invoice_id)?.file_id ?? e.invoice_id }
      }
    case 'decision': {
      const d = decisiones.find((x) => x.decision_id === e.decision_id)
      return {
        summary: `decisión → ${d?.result ?? '?'}`,
        payload: { decision_id: e.decision_id, result: d?.result ?? null }
      }
    }
    case 'override': {
      const o = overrides.find((x) => x.id === e.override_id)
      return {
        summary: o ? `${o.field_type}: ${o.before} → ${o.after} · ${o.who}` : 'override',
        payload: o
          ? { field_type: o.field_type, before: o.before, after: o.after, who: o.who, reason: o.reason }
          : {}
      }
    }
    default:
      return { summary: e.type, payload: {} }
  }
}

function logs(params: { q?: string; event_type?: string; invoice?: string; limit?: number; offset?: number }): LogsResponse {
  const types = [...new Set(eventos.map((e) => e.type))].sort()
  let filtrados = [...eventos]
  if (params.event_type) filtrados = filtrados.filter((e) => e.type === params.event_type)
  if (params.invoice) {
    // filtro por nombre de factura: se resuelve contra las tablas
    const aguja = params.invoice.toLowerCase()
    filtrados = filtrados.filter((e) => {
      const f = facturas.get(e.invoice_id)
      return (f?.file_id ?? '').toLowerCase().includes(aguja)
    })
  }
  if (params.q) {
    const needle = params.q.toLowerCase()
    filtrados = filtrados.filter((e) => {
      const factura = facturas.get(e.invoice_id)
      const paja = JSON.stringify(e) + ' ' + (factura?.file_id ?? '')
      return paja.toLowerCase().includes(needle)
    })
  }
  const limit = Math.max(1, Math.min(params.limit ?? 200, 1000))
  const offset = Math.max(0, params.offset ?? 0)
  const items = [...filtrados].reverse().slice(offset, offset + limit).map<LogItem>((e) => {
    const { summary, payload } = summaryDe(e)
    return {
      seq: e.seq,
      ts: e.ts,
      type: e.type,
      invoice_id: e.invoice_id,
      file_id: facturas.get(e.invoice_id)?.file_id ?? e.invoice_id,
      decision_id: e.decision_id ?? null,
      summary,
      payload
    }
  })
  return { total: filtrados.length, types, items }
}

// ---- ingesta sintética (jobs) --------------------------------------------

interface MockJob {
  job_id: string
  origin: string
  state: JobStatus['state']
  created_at: number
  finished_at: number | null
  items: JobStatus['items']
}

const mockJobs = new Map<string, MockJob>()

function jobSummary(j: MockJob): JobSummary {
  const done = j.items.filter((i) => i.status === 'done').length
  const error = j.items.filter((i) => i.status === 'error').length
  const pending = j.items.filter((i) => i.status === 'pending').length
  return {
    job_id: j.job_id,
    origin: j.origin,
    state: j.state,
    total: j.items.length,
    done,
    error,
    pending,
    created_at: j.created_at,
    finished_at: j.finished_at
  }
}

function jobStatus(j: MockJob): JobStatus {
  const s = jobSummary(j)
  return {
    job_id: s.job_id,
    origin: s.origin,
    state: s.state,
    created_at: s.created_at,
    finished_at: s.finished_at,
    error: null,
    counts: { total: s.total, done: s.done, error: s.error, pending: s.pending },
    items: j.items.map((i) => ({ ...i }))
  }
}

/** Ingesta sintética: valida igual que el backend y resuelve en segundo plano. */
async function ingest(files: { relPath: string; file: File }[]): Promise<IngestResponse> {
  const accepted: IngestResponse['accepted'] = []
  const rejected: IngestResponse['rejected'] = []
  const vistos = new Set<string>()
  for (const f of files) {
    const rel = f.relPath
    if (vistos.has(rel)) {
      rejected.push({ rel_path: rel, reason: 'ruta relativa duplicada en la petición' })
      continue
    }
    vistos.add(rel)
    const ext = rel.slice(rel.lastIndexOf('.')).toLowerCase()
    if (!['.pdf', '.png', '.jpg', '.jpeg'].includes(ext)) {
      rejected.push({ rel_path: rel, reason: 'extensión no soportada' })
      continue
    }
    if (f.file.size > 64 * 1024 * 1024) {
      rejected.push({ rel_path: rel, reason: 'fichero mayor de 64 MiB' })
      continue
    }
    accepted.push({
      file_id: rel.split('/').pop() ?? rel,
      file_key: hex(32, seedDe(rel)),
      sha256: hex(64, seedDe(rel + ':' + f.file.size)),
      rel_path: rel
    })
  }
  if (accepted.length === 0) {
    throw new Error(rejected[0]?.reason ?? 'ningún fichero aceptado')
  }
  const job_id = `job-${hex(8, seedDe(accepted.map((a) => a.rel_path).join('|')))}`
  const now = AHORA()
  const items: JobStatus['items'] = accepted.map((a) => ({
    file_id: a.file_id,
    file_key: a.file_key,
    sha256: a.sha256,
    status: 'pending',
    result: null,
    decision_id: null,
    scan_id: null,
    error: null,
    updated_at: now
  }))
  mockJobs.set(job_id, { job_id, origin: 'upload', state: 'running', created_at: now, finished_at: null, items })
  void (async () => {
    for (const item of items) {
      await new Promise<void>((resolve) => setTimeout(resolve, 400))
      item.status = 'done'
      item.result = item.file_id.toLowerCase().endsWith('.pdf') ? 'PAGAR' : 'ESCALAR'
      item.decision_id = `d-${hex(8, seedDe(item.file_id))}`
      item.scan_id = hex(8, seedDe(item.file_id + 'scan'))
      item.updated_at = AHORA()
    }
    const j = mockJobs.get(job_id)
    if (j) {
      j.state = 'complete'
      j.finished_at = AHORA()
    }
  })()
  return { job_id, accepted, rejected }
}

let mockConfig: RuntimeConfig = {
  mode: 'standalone',
  sync_url: '',
  vlm_url: '',
  vlm_model: '',
  local_vlm_fallback: false,
  server_api_key: '',
  firecrawl_api_key: '',
  cloud_vlm_api_key: '',
  typesafe_api_key: '',
  firecrawl_api_key_set: false,
  cloud_vlm_api_key_set: false,
  typesafe_api_key_set: false,
  configured: true
}
let mockSyncStatus: SyncStatus = {
  state: 'standalone',
  pending: false,
  last_sync: null,
  ok: true,
  error: null
}

// Claves de los últimos peldaños: el mock guarda el valor en claro y sirve la
// máscara, igual que el backend (nunca devuelve el secreto al leer).
let mockRungKeys = {
  firecrawl_api_key: '',
  cloud_vlm_api_key: '',
  typesafe_api_key: ''
}

function conClavesEnmascaradas(cfg: RuntimeConfig): RuntimeConfig {
  const mask = (value: string) => (value ? `****${value.slice(-4)}` : '')
  return {
    ...cfg,
    firecrawl_api_key: mask(mockRungKeys.firecrawl_api_key),
    firecrawl_api_key_set: mockRungKeys.firecrawl_api_key !== '',
    cloud_vlm_api_key: mask(mockRungKeys.cloud_vlm_api_key),
    cloud_vlm_api_key_set: mockRungKeys.cloud_vlm_api_key !== '',
    typesafe_api_key: mask(mockRungKeys.typesafe_api_key),
    typesafe_api_key_set: mockRungKeys.typesafe_api_key !== ''
  }
}

/** Vacío o máscara conservan la clave guardada; clear_keys borra las tres. */
function resolverClaveGuardada(guardada: string, entrada: string | undefined, clear: boolean): string {
  if (clear) return ''
  const raw = (entrada || '').trim()
  if (!raw || raw.startsWith('****') || raw.startsWith('••••')) return guardada
  return raw
}
// Estado VLM sintético: la referencia local se declara lista sin verificación
// real (no hay modelo ni binario en modo sintético).
let mockVlmStatus: VlmStatus = {
  mode: 'standalone',
  local_required: true,
  local_fallback: false,
  state: 'ready',
  downloaded: true,
  running: true,
  ready: true,
  detail: 'referencia sintética: sin verificación real',
  error: null,
  model: null,
  mmproj: null,
  binary: null
}

export const mockApi = {
  facturas: async () => [...facturas.values()].map(aFila),
  factura: async (id: string) => detalleDe(id),
  reprocesar: async (fileId: string) => reprocesar(fileId),
  revision: async () => revisionList(),
  resolve: async (invoiceId: string, body: ResolveInput) => resolver(invoiceId, body),
  ingest: async (files: { relPath: string; file: File }[]) => ingest(files),
  jobs: async () => ({ jobs: [...mockJobs.values()].map(jobSummary) }),
  job: async (jobId: string) => {
    const j = mockJobs.get(jobId)
    if (!j) throw new Error(`job ${jobId} no encontrado`)
    return jobStatus(j)
  },
  reglas: async () => REGLAS,
  salud: async () => SALUD,
  logs: async (params: { q?: string; event_type?: string; invoice?: string; limit?: number; offset?: number }) =>
    logs(params),
  getConfig: async () => conClavesEnmascaradas({ ...mockConfig }),
  saveConfig: async (cfg: RuntimeConfigInput) => {
    const standalone = cfg.mode === 'standalone'
    const clear = cfg.clear_keys === true
    mockRungKeys = {
      firecrawl_api_key: resolverClaveGuardada(mockRungKeys.firecrawl_api_key, cfg.firecrawl_api_key, clear),
      cloud_vlm_api_key: resolverClaveGuardada(mockRungKeys.cloud_vlm_api_key, cfg.cloud_vlm_api_key, clear),
      typesafe_api_key: resolverClaveGuardada(mockRungKeys.typesafe_api_key, cfg.typesafe_api_key, clear)
    }
    mockConfig = {
      mode: cfg.mode,
      sync_url: standalone ? '' : cfg.sync_url,
      vlm_url: standalone ? '' : cfg.vlm_url,
      vlm_model: standalone ? '' : cfg.vlm_model,
      local_vlm_fallback: standalone ? false : cfg.local_vlm_fallback,
      server_api_key: standalone ? '' : cfg.server_api_key,
      firecrawl_api_key: '',
      cloud_vlm_api_key: '',
      typesafe_api_key: '',
      firecrawl_api_key_set: false,
      cloud_vlm_api_key_set: false,
      typesafe_api_key_set: false,
      configured: true
    }
    mockSyncStatus = {
      state: cfg.mode === 'server' ? 'synced' : 'standalone',
      pending: false,
      last_sync: cfg.mode === 'server' ? Date.now() / 1000 : null,
      ok: true,
      error: null
    }
    mockVlmStatus = {
      ...mockVlmStatus,
      mode: cfg.mode,
      local_required: standalone,
      local_fallback: standalone ? false : cfg.local_vlm_fallback,
      state: standalone ? 'ready' : (cfg.local_vlm_fallback ? 'ready' : 'remote-only'),
      downloaded: true,
      running: true,
      ready: true
    }
    return { ...mockConfig }
  },
  vlmStatus: async () => ({ ...mockVlmStatus }),
  vlmProvision: async () => {
    mockVlmStatus = { ...mockVlmStatus, state: 'ready', downloaded: true, running: true, ready: true, error: null }
    return { ...mockVlmStatus }
  },
  sync: async () => {
    if (mockConfig.mode !== 'server') {
      throw new Error('La sincronización requiere modo servidor')
    }
    mockSyncStatus = {
      state: 'synced',
      pending: false,
      last_sync: Date.now() / 1000,
      ok: true,
      error: null
    }
    return { ok: true, pushed: 0, pulled: 0 }
  },
  syncStatus: async () => ({ ...mockSyncStatus })
}
