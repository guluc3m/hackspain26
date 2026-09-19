// Respuestas sintéticas para la UI: mismo contrato que el backend
// (src/albertitos/types.py y src/albertitos/api/app.py), sin motor de
// decisión ni escalera de extracción. Modo demo/desarrollo de interfaz.
//
// El estado es mutable y en memoria: override/reprocesar actualizan
// iteraciones y ledger sintético, como haría el store real, pero sin
// invocar ningún motor.

import type {
  Candidate,
  FacturaRow,
  InvoiceDetail,
  LogEvent,
  LogsResponse,
  OverrideIn,
  Reglas,
  Resultado,
  Salud
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

interface FacturaSeed {
  id: string
  file_id: string
  result: Resultado | null
  iterations: number
  confidence: number | null
  carpeta: string
  candidates: Record<string, Candidate[]>
  veredictos?: { code: string; verdict: 'PASS' | 'FAIL' | 'UNKNOWN'; reason: string }[]
  overridesPrevios?: {
    field_type: string
    before: unknown
    after: unknown
    who: string
    rung: string
    reason: string
    haceMin: number
  }[]
}

const CARPETA = '/data/lotes/caja-de-alberto'

const SEMILLAS: FacturaSeed[] = [
  {
    id: '5f0c3a2e-9b14-4c8d-a1e2-0a1b2c3d4e01',
    file_id: '2026-01-08_P001.pdf',
    result: 'PAGAR',
    iterations: 1,
    confidence: 0.92,
    carpeta: CARPETA,
    candidates: {
      nif: [cand('regex', 'B12345678', 0.95), cand('tesseract', 'B12345678', 0.88)],
      iban: [cand('regex', 'ES9121000418450200051332', 0.97), cand('tesseract', 'ES9121000418450200051332', 0.9)],
      total: [cand('regex', 121.0, 0.98), cand('tesseract', 121.0, 0.91)],
      iva_amount: [cand('regex', 21.0, 0.9)],
      fecha: [cand('regex', '2026-01-08', 0.93)],
      pedido: [cand('regex', 'P-2026-001', 0.94)]
    },
    veredictos: [
      { code: 'DATE_VALID_NOT_FUTURE', verdict: 'PASS', reason: 'fecha 2026-01-08 válida y no futura' },
      { code: 'IBAN_MATCHES_MASTER', verdict: 'PASS', reason: 'IBAN coincide con el maestro de B12345678' },
      { code: 'IVA_CONSISTENT', verdict: 'PASS', reason: 'base 100.00 + IVA 21.00 = total 121.00' },
      { code: 'NIF_IN_MASTER', verdict: 'PASS', reason: 'B12345678 presente en el maestro' },
      { code: 'NO_DOUBLE_PAYMENT', verdict: 'PASS', reason: 'P-2026-001 sin pago previo' },
      { code: 'ORDER_BELONGS_TO_SUPPLIER', verdict: 'PASS', reason: 'P-2026-001 pertenece a B12345678' },
      { code: 'ORDER_PENDING', verdict: 'PASS', reason: 'estado ERP de P-2026-001: PENDIENTE' },
      { code: 'TOTALS_MUST_MATCH', verdict: 'PASS', reason: 'importe igual al pedido (121.00, tolerancia 0.01)' }
    ]
  },
  {
    id: '5f0c3a2e-9b14-4c8d-a1e2-0a1b2c3d4e02',
    file_id: '2026-01-11_P007.pdf',
    result: 'NO_PAGAR',
    iterations: 1,
    confidence: 0.88,
    carpeta: CARPETA,
    candidates: {
      nif: [cand('regex', 'B87654321', 0.93)],
      iban: [cand('regex', 'ES7921000813610123456789', 0.95)],
      total: [cand('regex', 847.0, 0.96), cand('tesseract', 874.0, 0.62)],
      iva_amount: [cand('regex', 66.5, 0.87)],
      fecha: [cand('regex', '2026-01-11', 0.9)],
      pedido: [cand('regex', 'P-2026-002', 0.91)]
    },
    veredictos: [
      { code: 'DATE_VALID_NOT_FUTURE', verdict: 'PASS', reason: 'fecha 2026-01-11 válida y no futura' },
      { code: 'IBAN_MATCHES_MASTER', verdict: 'PASS', reason: 'IBAN coincide con el maestro de B87654321' },
      { code: 'IVA_CONSISTENT', verdict: 'PASS', reason: 'base 780.50 + IVA 66.50 = total 847.00' },
      { code: 'NIF_IN_MASTER', verdict: 'PASS', reason: 'B87654321 presente en el maestro' },
      { code: 'NO_DOUBLE_PAYMENT', verdict: 'PASS', reason: 'P-2026-002 sin pago previo' },
      { code: 'ORDER_BELONGS_TO_SUPPLIER', verdict: 'PASS', reason: 'P-2026-002 pertenece a B87654321' },
      { code: 'ORDER_PENDING', verdict: 'PASS', reason: 'estado ERP de P-2026-002: PENDIENTE' },
      { code: 'TOTALS_MUST_MATCH', verdict: 'FAIL', reason: 'importe 847.00 difiere del pedido (121.00 > 0.01)' }
    ]
  },
  {
    id: '5f0c3a2e-9b14-4c8d-a1e2-0a1b2c3d4e03',
    file_id: '2026-01-12_P002.pdf',
    result: 'ESCALAR',
    iterations: 2,
    confidence: 0.54,
    carpeta: CARPETA,
    candidates: {
      nif: [cand('regex', 'X1234567R', 0.9), cand('tesseract', 'X1234567R', 0.84)],
      iban: [cand('regex', 'ES1000492352082414205416', 0.91), cand('tesseract', 'ES1O00492352082414205416', 0.54)],
      total: [cand('regex', 60.5, 0.93), cand('vlm', 65.0, 0.71)],
      iva_amount: [cand('regex', 4.5, 0.79)],
      fecha: [cand('regex', '2026-01-12', 0.86)],
      pedido: [cand('tesseract', 'P-2026-003', 0.58), cand('vlm', 'P-2026-008', 0.61)]
    },
    veredictos: [
      { code: 'DATE_VALID_NOT_FUTURE', verdict: 'PASS', reason: 'fecha 2026-01-12 válida y no futura' },
      { code: 'IBAN_MATCHES_MASTER', verdict: 'PASS', reason: 'IBAN coincide con el maestro de X1234567R' },
      { code: 'IVA_CONSISTENT', verdict: 'UNKNOWN', reason: 'sin base extraída: no se puede verificar base + IVA' },
      { code: 'NIF_IN_MASTER', verdict: 'PASS', reason: 'X1234567R presente en el maestro' },
      { code: 'NO_DOUBLE_PAYMENT', verdict: 'UNKNOWN', reason: 'pedido ambiguo: P-2026-003 vs P-2026-008' },
      { code: 'ORDER_BELONGS_TO_SUPPLIER', verdict: 'UNKNOWN', reason: 'pedido ambiguo: no se cruza con el ERP con confianza' },
      { code: 'ORDER_PENDING', verdict: 'UNKNOWN', reason: 'pedido ambiguo: estado ERP no consultable' },
      { code: 'TOTALS_MUST_MATCH', verdict: 'PASS', reason: 'importe igual al pedido P-2026-003 (60.50, tolerancia 0.01)' }
    ],
    overridesPrevios: [
      {
        field_type: 'total',
        before: 65.0,
        after: 60.5,
        who: 'revisor',
        rung: 'review-ui',
        reason: 'corrección manual en revisión',
        haceMin: 95
      }
    ]
  },
  {
    id: '5f0c3a2e-9b14-4c8d-a1e2-0a1b2c3d4e04',
    file_id: '2026-01-23_P006.pdf',
    result: 'PAGAR',
    iterations: 1,
    confidence: 0.81,
    carpeta: CARPETA,
    candidates: {
      nif: [cand('regex', 'B12345678', 0.94)],
      iban: [cand('regex', 'ES9121000418450200051332', 0.92)],
      total: [cand('regex', 242.0, 0.95)],
      iva_amount: [cand('regex', 42.0, 0.81)],
      fecha: [cand('regex', '2026-01-23', 0.89)],
      pedido: [cand('regex', 'P-2026-004', 0.83)]
    },
    veredictos: [
      { code: 'DATE_VALID_NOT_FUTURE', verdict: 'PASS', reason: 'fecha 2026-01-23 válida y no futura' },
      { code: 'IBAN_MATCHES_MASTER', verdict: 'PASS', reason: 'IBAN coincide con el maestro de B12345678' },
      { code: 'IVA_CONSISTENT', verdict: 'PASS', reason: 'base 200.00 + IVA 42.00 = total 242.00' },
      { code: 'NIF_IN_MASTER', verdict: 'PASS', reason: 'B12345678 presente en el maestro' },
      { code: 'NO_DOUBLE_PAYMENT', verdict: 'PASS', reason: 'P-2026-004 sin pago previo' },
      { code: 'ORDER_BELONGS_TO_SUPPLIER', verdict: 'PASS', reason: 'P-2026-004 pertenece a B12345678' },
      { code: 'ORDER_PENDING', verdict: 'PASS', reason: 'estado ERP de P-2026-004: PENDIENTE' },
      { code: 'TOTALS_MUST_MATCH', verdict: 'PASS', reason: 'importe igual al pedido (242.00, tolerancia 0.01)' }
    ]
  },
  {
    id: '5f0c3a2e-9b14-4c8d-a1e2-0a1b2c3d4e05',
    file_id: '2026-01-17_P011.pdf',
    result: null,
    iterations: 0,
    confidence: null,
    carpeta: CARPETA,
    candidates: {}
  },
  {
    id: '5f0c3a2e-9b14-4c8d-a1e2-0a1b2c3d4e06',
    file_id: 'inventario_enero.xlsx',
    result: null,
    iterations: 0,
    confidence: null,
    carpeta: '/data/lotes/caja-de-alberto/excel',
    candidates: {}
  },
  {
    id: '5f0c3a2e-9b14-4c8d-a1e2-0a1b2c3d4e07',
    file_id: 'facturas_proveedores.xlsx',
    result: null,
    iterations: 0,
    confidence: null,
    carpeta: '/data/lotes/caja-de-alberto/excel',
    candidates: {}
  }
]

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

// ---- estado mutable en memoria -------------------------------------------

interface Fila {
  row: FacturaRow
  detalle: InvoiceDetail
}

const filas = new Map<string, Fila>()
const eventos: LogEvent[] = []

function snapshotJSON(): string {
  return JSON.stringify({
    rule_set_version: REGLAS.rule_set_version,
    thresholds: REGLAS.thresholds,
    extractor_versions: { regex: '1.0', tesseract: '5.x', vlm: 'PaddleOCR-VL-1.6-q8' },
    master_sha256: hex(64, 42),
    config_version: REGLAS.config_version
  })
}

function construirDetalle(seed: FacturaSeed, decidido: Resultado | null): InvoiceDetail {
  const ahora = AHORA()
  return {
    invoice: {
      id: seed.id,
      file_id: seed.file_id,
      sha256: hex(64, seedDe(seed.file_id)),
      first_seen: ahora - 3600,
      last_seen: ahora - 60,
      status: decidido ?? 'pendiente',
      source_path: `${seed.carpeta}/${seed.file_id}`
    },
    fields: seed.candidates,
    decision:
      decidido === null
        ? null
        : {
            invoice_id: seed.id,
            run_id: REGLAS.config_version,
            result: decidido,
            config_snapshot: snapshotJSON(),
            timestamp: ahora - 120
          },
    rule_evaluations: (seed.veredictos ?? []).map((v) => ({
      code: v.code,
      verdict: v.verdict,
      reason: v.reason,
      consumed: { fuente: 'sintético' },
      timestamp: ahora - 120
    })),
    overrides: (seed.overridesPrevios ?? []).map((o, i) => ({
      id: i + 1,
      invoice_id: seed.id,
      field_type: o.field_type,
      before: JSON.stringify(o.before),
      after: JSON.stringify(o.after),
      who: o.who,
      rung: o.rung,
      reason: o.reason,
      timestamp: ahora - o.haceMin * 60
    }))
  }
}

for (const seed of SEMILLAS) {
  filas.set(seed.id, { row: null as unknown as FacturaRow, detalle: construirDetalle(seed, seed.result) })
}

function refrescarFila(f: Fila): FacturaRow {
  const d = f.detalle
  f.row = {
    id: d.invoice.id,
    file_id: d.invoice.file_id,
    status: d.invoice.status,
    source_path: d.invoice.source_path || null,
    folder: d.invoice.source_path ? d.invoice.source_path.split('/').slice(0, -1).join('/') : null,
    result: d.decision?.result ?? null,
    decided_at: d.decision?.timestamp ?? null,
    iterations: iteracionesPorFactura.get(d.invoice.id) ?? 0,
    confidence:
      Object.keys(d.fields).length === 0
        ? null
        : Math.min(
            ...Object.values(d.fields).map((cs) => Math.max(...cs.map((c) => c.confidence)))
          )
  }
  return f.row
}

const iteracionesPorFactura = new Map<string, number>()
for (const seed of SEMILLAS) {
  if (seed.iterations > 0) iteracionesPorFactura.set(seed.id, seed.iterations)
}

function log(type: string, payload: Record<string, unknown>): void {
  eventos.push({ seq: eventos.length + 1, ts: AHORA(), type, ...payload })
}

// eventos iniciales (cronológico; /api/logs devuelve los más recientes primero)
for (const seed of SEMILLAS) {
  if (seed.iterations === 0) continue
  log('invoice_seen', {
    invoice_id: seed.id,
    file_id: seed.file_id,
    sha256: hex(64, seedDe(seed.file_id))
  })
  if (seed.result) {
    log('decision', {
      invoice_id: seed.id,
      file_id: seed.file_id,
      result: seed.result,
      run_id: REGLAS.config_version
    })
  }
}
for (const seed of SEMILLAS) {
  for (const o of seed.overridesPrevios ?? []) {
    log('override', {
      invoice_id: seed.id,
      field_type: o.field_type,
      before: o.before,
      after: o.after,
      who: o.who,
      rung: o.rung,
      reason: o.reason
    })
  }
}
log('item_error', {
  file_id: 'factura_ilegible.pdf',
  error: 'DependencyError: zxing-cpp ausente y sin OCR disponible (skipped:dep)'
})

for (const f of filas.values()) refrescarFila(f)

// ---- API sintética (misma forma que el backend) ---------------------------

function detalleDe(id: string): InvoiceDetail {
  const f = filas.get(id)
  if (!f) throw new Error(`/api/facturas/${id}: 404`)
  return f.detalle
}

function reprocesar(fileId: string): { file_id: string; result: Resultado } {
  const f = [...filas.values()].find((x) => x.detalle.invoice.file_id === fileId)
  if (!f) throw new Error(`/api/reprocesar/${fileId}: 404`)
  const esPdf = fileId.toLowerCase().endsWith('.pdf')

  if (f.detalle.decision === null) {
    // respuesta sintética del procesado: PDF -> PAGAR (con campos),
    // no-PDF -> ESCALAR (sin campos, como el motor: sin evaluaciones ⇒ ESCALAR)
    if (esPdf) {
      const seed = SEMILLAS.find((s) => s.file_id === fileId)
      f.detalle.fields =
        seed?.candidates ??
        {
          nif: [cand('regex', 'B12345678', 0.9)],
          total: [cand('regex', 121.0, 0.9)]
        }
      f.detalle.rule_evaluations = (seed?.veredictos ?? []).map((v) => ({
        code: v.code,
        verdict: v.verdict,
        reason: v.reason,
        consumed: { fuente: 'sintético' },
        timestamp: AHORA()
      }))
      f.detalle.decision = {
        invoice_id: f.detalle.invoice.id,
        run_id: REGLAS.config_version,
        result: 'PAGAR',
        config_snapshot: snapshotJSON(),
        timestamp: AHORA()
      }
    } else {
      f.detalle.decision = {
        invoice_id: f.detalle.invoice.id,
        run_id: REGLAS.config_version,
        result: 'ESCALAR',
        config_snapshot: snapshotJSON(),
        timestamp: AHORA()
      }
    }
  }

  f.detalle.invoice.status = f.detalle.decision.result
  f.detalle.invoice.last_seen = AHORA()
  iteracionesPorFactura.set(f.detalle.invoice.id, (iteracionesPorFactura.get(f.detalle.invoice.id) ?? 0) + 1)
  log('invoice_seen', {
    invoice_id: f.detalle.invoice.id,
    file_id: fileId,
    sha256: f.detalle.invoice.sha256
  })
  log('decision', {
    invoice_id: f.detalle.invoice.id,
    file_id: fileId,
    result: f.detalle.decision.result,
    run_id: REGLAS.config_version
  })
  refrescarFila(f)
  return { file_id: fileId, result: f.detalle.decision.result }
}

function override(invoiceId: string, body: OverrideIn): { ok: boolean } {
  const f = filas.get(invoiceId)
  if (!f) throw new Error(`/api/revision/${invoiceId}/override: 404`)
  const previos = f.detalle.overrides
  previos.push({
    id: previos.length + 1,
    invoice_id: f.detalle.invoice.id,
    field_type: body.field_type,
    before: JSON.stringify(body.before),
    after: JSON.stringify(body.after),
    who: body.who,
    rung: body.rung,
    reason: body.reason,
    timestamp: AHORA()
  })
  log('override', {
    invoice_id: f.detalle.invoice.id,
    field_type: body.field_type,
    before: body.before,
    after: body.after,
    who: body.who,
    rung: body.rung,
    reason: body.reason
  })
  return { ok: true }
}

function logs(params: { q?: string; event_type?: string; limit?: number; offset?: number }): LogsResponse {
  let filtrados = [...eventos]
  const types = [...new Set(filtrados.map((e) => String(e.type)))].sort()
  if (params.event_type) filtrados = filtrados.filter((e) => e.type === params.event_type)
  if (params.q) {
    const needle = params.q.toLowerCase()
    filtrados = filtrados.filter((e) => JSON.stringify(e).toLowerCase().includes(needle))
  }
  const limit = Math.max(1, Math.min(params.limit ?? 200, 1000))
  const offset = Math.max(0, params.offset ?? 0)
  const items = filtrados.slice(offset, offset + limit).reverse()
  return { total: filtrados.length, types, items }
}

export const mockApi = {
  facturas: async () => [...filas.values()].map((f) => ({ ...refrescarFila(f) })),
  factura: async (id: string) => detalleDe(id),
  override: async (invoiceId: string, body: OverrideIn) => override(invoiceId, body),
  reprocesar: async (fileId: string) => reprocesar(fileId),
  reglas: async () => REGLAS,
  salud: async () => SALUD,
  logs: async (params: { q?: string; event_type?: string; limit?: number; offset?: number }) =>
    logs(params)
}
