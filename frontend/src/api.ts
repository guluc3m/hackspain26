// Contrato de datos de la UI. Todo lo mostrado proviene de la base de datos
// (sqlite) que expone el backend; mientras la conexión real está vacía, los
// datos son la referencia sintética de src/mock/data.ts (targets *_syncth).

import { mockApi } from './mock/data'

export type Resultado = 'PAGAR' | 'NO_PAGAR' | 'ESCALAR'
export type RuleVerdict = 'PASS' | 'FAIL' | 'UNKNOWN'
export type LogType = 'invoice_seen' | 'decision' | 'override'

/** Factura: fila de la tabla invoices de la base de datos. */
export interface FacturaRow {
  id: string
  file_id: string
  status: string
  source_path: string | null
  folder: string | null
  result: Resultado | null // de la última decisión
  decision_id: string | null // ID de la última decisión
  decided_at: number | null
  iterations: number // decisiones registradas para esta factura
  confidence: number | null
}

/** Un candidato de lectura: nunca se colapsan en la base de datos. */
export interface Candidate {
  extractor: string
  value: unknown
  confidence: number
}

/** Decisión del motor: siempre con su ID asignado. */
export interface DecisionRecord {
  decision_id: string
  invoice_id: string
  result: Resultado
  timestamp: number
}

export interface RuleEvaluationRow {
  code: string
  verdict: RuleVerdict
  reason: string
  consumed: unknown
  timestamp: number
}

export interface OverrideRow {
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

export interface InvoiceDetail {
  invoice: {
    id: string
    file_id: string
    sha256: string
    first_seen: number
    last_seen: number
    status: string
    source_path: string
  }
  fields: Record<string, Candidate[]>
  decision: DecisionRecord | null // última decisión
  rule_evaluations: RuleEvaluationRow[] // las de la última decisión
  overrides: OverrideRow[]
}

export interface Reglas {
  rule_set_version: string
  config_version: string
  enabled: string[]
  thresholds: Record<string, Record<string, number>>
}

export interface Salud {
  tesseract: string
  'llama-server': string
  cloud_vlm: string
  store: string
}

/**
 * Entrada del log: referencia mínima (tipo + IDs). Sin reglas ni payloads:
 * el detalle vive en la base de datos y se resuelve al mostrarlo
 * (`resumen`) o al abrir la traza de la factura.
 */
export interface LogItem {
  seq: number
  ts: number | null
  type: LogType
  invoice_id: string | null
  decision_id: string | null
  resumen: string
}

export interface LogsResponse {
  total: number
  types: string[]
  items: LogItem[]
}

export interface OverrideIn {
  field_type: string
  before: unknown
  after: unknown
  who: string
  rung: string
  reason: string
}

/** Contrato de la capa de datos: referencia sintética o conexión real. */
export interface Api {
  facturas(): Promise<FacturaRow[]>
  factura(id: string): Promise<InvoiceDetail>
  override(invoiceId: string, body: OverrideIn): Promise<{ ok: boolean }>
  reprocesar(fileId: string): Promise<{ file_id: string; result: Resultado }>
  reglas(): Promise<Reglas>
  salud(): Promise<Salud>
  logs(params: { q?: string; event_type?: string; limit?: number; offset?: number }): Promise<LogsResponse>
}

// Conexión real: vacía a propósito. Se rellenará cuando el backend exponga
// la base de datos; la referencia de datos es la sintética.
function noConectado(): never {
  throw new Error('conexión real vacía: usa los targets *_syncth (datos sintéticos)')
}

const realApi: Api = {
  facturas: noConectado,
  factura: noConectado,
  override: noConectado,
  reprocesar: noConectado,
  reglas: noConectado,
  salud: noConectado,
  logs: noConectado
}

export const SINTETICO: boolean = import.meta.env.MODE === 'syncth'

export const api: Api = SINTETICO ? mockApi : realApi

// ---- helpers de presentación -------------------------------------------

export function fileExt(fileId: string): string {
  const i = fileId.lastIndexOf('.')
  return i === -1 ? '—' : fileId.slice(i + 1).toUpperCase()
}

export function fmtValor(v: unknown): string {
  if (v === null || v === undefined) return '—'
  return typeof v === 'object' ? JSON.stringify(v) : String(v)
}

export function fmtHora(ts: number | null | undefined): string {
  if (!ts) return '—'
  return new Date(ts * 1000).toLocaleString('es-ES')
}

/** Índice del candidato líder: mayor confianza (empate → el primero). */
export function liderIndex(cs: Candidate[]): number {
  return cs.reduce((best, c, i) => (c.confidence > cs[best].confidence ? i : best), 0)
}

/**
 * Confirmación de lectura: override antes=después (candidato líder de cada
 * campo) y reprocesado; la nueva decisión se registra con su propio ID.
 */
export async function confirmarLectura(invoiceId: string, reason = 'confirmación en revisión'): Promise<void> {
  const detail = await api.factura(invoiceId)
  for (const [fieldType, cs] of Object.entries(detail.fields)) {
    if (cs.length === 0) continue
    const lider = cs[liderIndex(cs)]
    await api.override(invoiceId, {
      field_type: fieldType,
      before: lider.value,
      after: lider.value,
      who: 'revisor',
      rung: 'review-ui',
      reason
    })
  }
  await api.reprocesar(detail.invoice.file_id)
}
