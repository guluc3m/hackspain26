// Cliente tipado del backend (src/albertitos). Espeja types.py y las
// respuestas de src/albertitos/api/app.py. En modo 'mock' responde con
// datos sintéticos (src/mock/data.ts), sin invocar ningún motor.

import { mockApi } from './mock/data'

export type Resultado = 'PAGAR' | 'NO_PAGAR' | 'ESCALAR'
export type RuleVerdict = 'PASS' | 'FAIL' | 'UNKNOWN'

/** Fila de /api/facturas (enriquecida: carpeta, iteraciones, confianza). */
export interface FacturaRow {
  id: string
  file_id: string
  status: string
  source_path: string | null
  folder: string | null
  result: Resultado | null
  decided_at: number | null
  iterations: number
  confidence: number | null
}

/** Un candidato de lectura: nunca se colapsan en el store (types.py). */
export interface Candidate {
  extractor: string
  value: unknown
  confidence: number
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
  before: string // JSON en texto (columna del store)
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
  decision: {
    invoice_id: string
    run_id: string
    result: Resultado
    config_snapshot: string // JSON en texto
    timestamp: number
  } | null
  rule_evaluations: RuleEvaluationRow[]
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

/** Evento del ledger append-only. seq = posición en el fichero. */
export type LogEvent = { seq: number; ts: number | null; type: string } & Record<string, unknown>

export interface LogsResponse {
  total: number
  types: string[]
  items: LogEvent[]
}

export interface OverrideIn {
  field_type: string
  before: unknown
  after: unknown
  who: string
  rung: string
  reason: string
}

async function get<T>(url: string): Promise<T> {
  const r = await fetch(url)
  if (!r.ok) throw new Error(`${url}: ${r.status}`)
  return r.json() as Promise<T>
}

async function post<T>(url: string, body?: unknown): Promise<T> {
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body)
  })
  if (!r.ok) throw new Error(`${url}: ${r.status}`)
  return r.json() as Promise<T>
}

/** Contrato de la capa de datos: respuestas del backend o sintéticas. */
export interface Api {
  facturas(): Promise<FacturaRow[]>
  factura(id: string): Promise<InvoiceDetail>
  override(invoiceId: string, body: OverrideIn): Promise<{ ok: boolean }>
  reprocesar(fileId: string): Promise<{ file_id: string; result: Resultado }>
  reglas(): Promise<Reglas>
  salud(): Promise<Salud>
  logs(params: { q?: string; event_type?: string; limit?: number; offset?: number }): Promise<LogsResponse>
}

const realApi: Api = {
  facturas: () => get<FacturaRow[]>('/api/facturas'),
  factura: (id: string) => get<InvoiceDetail>(`/api/facturas/${id}`),
  override: (invoiceId: string, body: OverrideIn) =>
    post<{ ok: boolean }>(`/api/revision/${invoiceId}/override`, body),
  reprocesar: (fileId: string) =>
    post<{ file_id: string; result: Resultado }>(`/api/reprocesar/${encodeURIComponent(fileId)}`),
  reglas: () => get<Reglas>('/api/reglas'),
  salud: () => get<Salud>('/api/salud'),
  logs: (params) => {
    const usp = new URLSearchParams()
    if (params.q) usp.set('q', params.q)
    if (params.event_type) usp.set('event_type', params.event_type)
    if (params.limit) usp.set('limit', String(params.limit))
    if (params.offset) usp.set('offset', String(params.offset))
    const qs = usp.toString()
    return get<LogsResponse>(`/api/logs${qs ? `?${qs}` : ''}`)
  }
}

/**
 * Modo de la interfaz:
 *  - 'mock' (por defecto): respuestas sintéticas, sin motor de decisión ni
 *    de extracción (src/mock/data.ts). Para desarrollar/demostrar la UI.
 *  - 'real': contra la API FastAPI (uv run albertitos serve).
 * Se selecciona con VITE_API_MODE=real (build o dev).
 */
export const MODO_API: 'mock' | 'real' = import.meta.env.VITE_API_MODE === 'real' ? 'real' : 'mock'

export const api: Api = MODO_API === 'real' ? realApi : mockApi

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
 * campo) y reprocesado. La decisión la recalcula el motor determinista.
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
