// Contrato compartido con FastAPI/PouchDB; *_syncth mantiene la demo local.

import { mockApi } from './mock/data'

export type Resultado = 'PAGAR' | 'NO_PAGAR' | 'ESCALAR'
export type RuleVerdict = 'PASS' | 'FAIL' | 'UNKNOWN'
export type LogType = 'invoice_seen' | 'decision' | 'override' | 'feature' | 'fields' | 'item_error'

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
  id: number | string
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
  seq: number | string
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
export interface RuntimeConfig {
  mode: 'standalone' | 'server'
  sync_url: string
  vlm_url: string
  vlm_model: string
}

export interface SyncStatus {
  ok: boolean
  state: 'idle' | 'syncing' | 'synced' | 'error' | 'standalone'
  error?: string | null
}

/** Contrato de la capa de datos: referencia sintética o conexión real. */
export interface Api {
  facturas(): Promise<FacturaRow[]>
  factura(id: string): Promise<InvoiceDetail>
  override(invoiceId: string, body: OverrideIn): Promise<{ ok: boolean }>
  reprocesar(fileId: string, fileKey?: string): Promise<{ file_id: string; result: Resultado }>
  reglas(): Promise<Reglas>
  salud(): Promise<Salud>
  logs(params: { q?: string; event_type?: string; invoice?: string; limit?: number; offset?: number }): Promise<LogsResponse>
  getConfig(): Promise<RuntimeConfig>
  saveConfig(config: RuntimeConfig): Promise<RuntimeConfig>
  sync(): Promise<{ ok: boolean; [key: string]: unknown }>
  syncStatus(): Promise<SyncStatus>
}

async function request<T>(path: string, body?: unknown, method = 'POST'): Promise<T> {
  const options: RequestInit = {}
  if (body !== undefined) {
    options.method = method
    options.headers = { 'Content-Type': 'application/json' }
    options.body = JSON.stringify(body)
  } else if (method !== 'POST') {
    options.method = method
  }
  const response = await fetch(path, options)
  if (!response.ok) {
    let errorText = await response.text()
    try {
      const parsed = JSON.parse(errorText)
      if (parsed && typeof parsed === 'object' && 'detail' in parsed) {
        errorText = String(parsed.detail)
      }
    } catch {
      // use raw errorText
    }
    throw new Error(errorText || `Error HTTP ${response.status}`)
  }
  return response.json() as Promise<T>
}

const realApi: Api = {
  facturas: () => request('/api/facturas', undefined, 'GET'),
  factura: id => request(`/api/facturas/${encodeURIComponent(id)}`, undefined, 'GET'),
  override: (id, body) => request(`/api/revision/${encodeURIComponent(id)}/override`, body, 'POST'),
  reprocesar: (id, key) => request(`/api/reprocesar/${encodeURIComponent(id)}${key ? '?file_key=' + encodeURIComponent(key) : ''}`, {}, 'POST'),
  reglas: () => request('/api/reglas', undefined, 'GET'),
  salud: () => request('/api/salud', undefined, 'GET'),
  logs: params => request('/api/logs?' + new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined).map(([k, v]) => [k, String(v)])
  ), undefined, 'GET'),
  getConfig: () => request('/api/config', undefined, 'GET'),
  saveConfig: config => request('/api/config', config, 'PUT'),
  sync: () => request('/api/sync', {}, 'POST'),
  syncStatus: () => request('/api/sync/status', undefined, 'GET')
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
  await api.reprocesar(detail.invoice.file_id, detail.invoice.id)
}
