// Contrato compartido con FastAPI/PouchDB; *_syncth mantiene la demo local.

import { mockApi } from './mock/data'

export type Resultado = 'PAGAR' | 'NO_PAGAR' | 'ESCALAR'
export type RuleVerdict = 'PASS' | 'FAIL' | 'UNKNOWN'
export type LogType = 'invoice_seen' | 'decision' | 'override' | 'feature' | 'fields' | 'item_error'
export type ReviewState = 'pending' | 'resolved' | 'not_required'

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
  /** Disputa pendiente de revisión humana. */
  disputed?: boolean
  /** Excluida de la replicación CouchDB hasta resolverse. */
  withheld_from_sync?: boolean
  review_state?: ReviewState
  resolution_id?: string | null
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
  /** Disputa pendiente de revisión humana. */
  disputed?: boolean
  /** Excluida de la replicación CouchDB hasta resolverse. */
  withheld_from_sync?: boolean
  review_state?: ReviewState
  resolution_id?: string | null
  /** Última resolución humana registrada, si existe. */
  resolution?: Resolution | null
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
 * Entrada del log: referencia mínima (tipo + IDs) más un resumen semántico y su
 * payload estructurado. El detalle vive en la base de datos y se resuelve al
 * mostrarlo (`summary`) o al abrir la traza de la factura.
 */
export interface LogItem {
  seq: number | string
  ts: number | null
  type: LogType
  invoice_id: string | null
  /** Nombre exacto del fichero (basename), ya resuelto por el backend. */
  file_id: string | null
  decision_id: string | null
  /** Resumen semántico corto resuelto por el backend (nunca JSON crudo). */
  summary: string
  /** Payload estructurado del evento, para mostrar en crudo solo bajo demanda. */
  payload: object | null
}

export interface LogsResponse {
  total: number
  types: string[]
  items: LogItem[]
}

/** Elemento de la cola de revisión (GET /api/revision). */
export interface ReviewItem {
  file_key: string
  file_id: string
  result: Resultado
  decision_id: string
  scan_id: string
  review_state: ReviewState
  reason: string
  since: number
}

/** Resolución humana registrada: afecta solo a la extracción, no al pago. */
export interface Resolution {
  who: string
  reason: string
  accepted: string[]
  corrected: Record<string, string>
  timestamp: number
}

/** Payload de POST /api/revision/{file_key}/resolve. */
export interface ResolveInput {
  who: string
  reason: string
  /** Campos cuya lectura actual se confirma (before = after). */
  accepted: string[]
  /** Campos corregidos a un valor nuevo (before = elegido, after = valor). */
  corrected: Record<string, unknown>
  /** Decisión cargada por la UI: un resolve obsoleto falla con 409. */
  expected_decision_id: string
}

export interface ResolveResponse {
  ok: boolean
  resolution_id: string
  decision_id: string
  result: Resultado
  review_state: ReviewState
  disputed: boolean
}
export interface RuntimeConfig {
  mode: 'standalone' | 'server'
  sync_url: string
  vlm_url: string
  vlm_model: string
  local_vlm_fallback: boolean
  /** Clave de API del servidor (solo modo servidor); nunca se muestra ni se registra. */
  server_api_key: string
  /**
   * Claves de los últimos peldaños (Firecrawl, VLM cloud y TypeSafe System One):
   * opcionales y válidas en ambos modos, guardadas solo en este dispositivo.
   * Al leer llegan enmascaradas ("****abcd"); vacío = sin clave (peldaño omitido).
   */
  firecrawl_api_key: string
  cloud_vlm_api_key: string
  typesafe_api_key: string
  /** Derivados por el backend: hay clave guardada, sin revelar el valor. */
  firecrawl_api_key_set: boolean
  cloud_vlm_api_key_set: boolean
  typesafe_api_key_set: boolean
  /** Derivado por el backend desde la base de datos; nunca autoridad del payload. */
  configured: boolean
}

/**
 * Payload de PUT /api/config: `configured` lo deriva el backend.
 *
 * Claves de los últimos peldaños: campo ausente o vacío y la máscara que
 * devuelve GET conservan la clave guardada; cualquier otro valor no vacío la
 * reemplaza; `clear_keys: true` borra las tres. `server_api_key` se guarda tal cual.
 */
export interface RuntimeConfigInput {
  mode: 'standalone' | 'server'
  sync_url: string
  vlm_url: string
  vlm_model: string
  local_vlm_fallback: boolean
  server_api_key: string
  firecrawl_api_key?: string
  cloud_vlm_api_key?: string
  typesafe_api_key?: string
  clear_keys?: boolean
}

export type VlmState = 'idle' | 'downloading' | 'starting' | 'ready' | 'error' | 'remote-only'

export interface VlmStatus {
  mode: 'standalone' | 'server'
  local_required: boolean
  local_fallback: boolean
  state: VlmState
  downloaded: boolean
  running: boolean
  /** `true` solo con el modelo en ejecución y sano, no solo descargado. */
  ready: boolean
  detail: string
  error: string | null
  /** 0..1 medido en disco (<fichero>.part vs tamaño esperado); null si nada es medible aún. */
  progress?: number | null
  bytes_done?: number
  bytes_total?: number
  /** Fichero de pesos en descarga ahora mismo, si lo hay. */
  file?: string | null
  model: string | null
  mmproj: string | null
  binary: string | null
}

export interface SyncStatus {
  state: 'idle' | 'syncing' | 'synced' | 'pending' | 'error' | 'standalone'
  pending: boolean
  last_sync?: number | null
  /** Compatibilidad con respuestas previas. */
  ok?: boolean
  error?: string | null
}

/** Ingesta: subida de ficheros y trabajos de procesamiento (POST /api/ingest). */
export interface IngestAccepted {
  file_id: string
  file_key: string
  sha256: string
  rel_path: string
}
export interface IngestRejected {
  rel_path: string
  reason: string
}
export interface IngestResponse {
  job_id: string
  accepted: IngestAccepted[]
  rejected: IngestRejected[]
}

export type JobState = 'queued' | 'running' | 'complete' | 'failed'

export interface JobItem {
  file_id: string
  file_key: string
  sha256: string
  status: 'done' | 'error' | 'pending'
  result: Resultado | null
  decision_id: string | null
  scan_id: string | null
  error: string | null
  updated_at: number
}
export interface JobCounts {
  total: number
  done: number
  error: number
  pending: number
}
export interface JobStatus {
  job_id: string
  origin: string
  state: JobState
  created_at: number
  finished_at: number | null
  /** Fallo de arranque del worker (nunca un estancamiento silencioso). */
  error: string | null
  counts: JobCounts
  items: JobItem[]
}
export interface JobSummary {
  job_id: string
  origin: string
  state: JobState
  total: number
  done: number
  error: number
  pending: number
  created_at: number
  finished_at: number | null
}

/** Contrato de la capa de datos: referencia sintética o conexión real. */
export interface Api {
  facturas(): Promise<FacturaRow[]>
  factura(id: string): Promise<InvoiceDetail>
  reprocesar(fileId: string, fileKey?: string): Promise<{ file_id: string; result: Resultado }>
  revision(): Promise<{ items: ReviewItem[] }>
  resolve(fileKey: string, body: ResolveInput): Promise<ResolveResponse>
  ingest(files: { relPath: string; file: File }[]): Promise<IngestResponse>
  jobs(): Promise<{ jobs: JobSummary[] }>
  job(jobId: string): Promise<JobStatus>
  reglas(): Promise<Reglas>
  salud(): Promise<Salud>
  logs(params: { q?: string; event_type?: string; invoice?: string; limit?: number; offset?: number }): Promise<LogsResponse>
  getConfig(): Promise<RuntimeConfig>
  saveConfig(config: RuntimeConfigInput): Promise<RuntimeConfig>
  vlmStatus(): Promise<VlmStatus>
  vlmProvision(): Promise<VlmStatus>
  sync(): Promise<{ ok: boolean; [key: string]: unknown }>
  syncStatus(): Promise<SyncStatus>
}

async function handleResponse<T>(response: Response): Promise<T> {
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

let authKey: string | null = null


async function request<T>(path: string, body?: unknown, method = 'POST', inner = false): Promise<T> {
  // Resolución de la clave fuera del camino de request(): pedir /api/config con
  // inner=true evita la recursión authHeader↔request (P0 fix). Un solo intento:
  // si falla, authKey='' y las llamadas siguen sin cabecera (401 visible).
  if (!SINTETICO && authKey === null && !inner) {
    authKey = await fetch('/api/config').then(handleResponse<{ server_api_key: string }>)
      .then(cfg => cfg.server_api_key || '')
      .catch(() => '')
  }
  const options: RequestInit = { headers: authKey ? { Authorization: `Bearer ${authKey}` } : {} }
  if (body !== undefined) {
    options.method = method
    options.headers = { ...options.headers, 'Content-Type': 'application/json' }
    options.body = JSON.stringify(body)
  } else if (method !== 'POST') {
    options.method = method
  }
  return handleResponse<T>(await fetch(path, options))
}

/** Subida multipart: cada fichero va como parte `files` con su ruta relativa. */
async function requestForm<T>(path: string, form: FormData): Promise<T> {
  if (!SINTETICO && authKey === null) {
    await request('/api/config', undefined, 'GET', true).catch(() => undefined)
  }
  return handleResponse<T>(await fetch(path, { method: 'POST', body: form, headers: authKey ? { Authorization: `Bearer ${authKey}` } : {} }))
}


const realApi: Api = {
  facturas: () => request('/api/facturas', undefined, 'GET'),
  factura: id => request(`/api/facturas/${encodeURIComponent(id)}`, undefined, 'GET'),
  reprocesar: (id, key) => request(`/api/reprocesar/${encodeURIComponent(id)}${key ? '?file_key=' + encodeURIComponent(key) : ''}`, {}, 'POST'),
  revision: () => request('/api/revision', undefined, 'GET'),
  resolve: (id, body) => request(`/api/revision/${encodeURIComponent(id)}/resolve`, body, 'POST'),
  ingest: files => {
    const form = new FormData()
    for (const f of files) form.append('files', f.file, f.relPath)
    return requestForm('/api/ingest', form)
  },
  jobs: () => request('/api/jobs', undefined, 'GET'),
  job: id => request(`/api/jobs/${encodeURIComponent(id)}`, undefined, 'GET'),
  reglas: () => request('/api/reglas', undefined, 'GET'),
  salud: () => request('/api/salud', undefined, 'GET'),
  logs: params => request('/api/logs?' + new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined).map(([k, v]) => [k, String(v)])
  ), undefined, 'GET'),
  getConfig: () => request('/api/config', undefined, 'GET'),
  saveConfig: config => request('/api/config', config, 'PUT'),
  vlmStatus: () => request('/api/vlm/status', undefined, 'GET'),
  vlmProvision: () => request('/api/vlm/provision', {}, 'POST'),
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
 * Confirmación de lectura: acepta el candidato líder de cada campo y resuelve
 * la revisión. El motor recalcula la decisión de forma determinista; nunca se
 * fuerza el pago desde la UI.
 */
export async function confirmarLectura(invoiceId: string, reason = 'confirmación en revisión'): Promise<void> {
  const detail = await api.factura(invoiceId)
  const accepted = Object.entries(detail.fields)
    .filter(([, cs]) => cs.length > 0)
    .map(([fieldType]) => fieldType)
  await api.resolve(invoiceId, {
    who: 'revisor',
    reason,
    accepted,
    corrected: {},
    expected_decision_id: detail.decision?.decision_id ?? ''
  })
}
