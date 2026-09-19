export type Resultado = 'PAGAR' | 'NO_PAGAR' | 'ESCALAR'

export interface Factura {
  id: string
  file_id: string
  status: string
  result: Resultado | null
  timestamp: number | null
}

export interface Reglas {
  config_version: string
  enabled: string[]
  thresholds: Record<string, Record<string, number>>
}

async function get<T>(url: string): Promise<T> {
  const r = await fetch(url)
  if (!r.ok) throw new Error(`${url}: ${r.status}`)
  return r.json()
}

export const api = {
  facturas: () => get<Factura[]>('/api/facturas'),
  factura: (id: string) => get<Record<string, unknown>>(`/api/facturas/${id}`),
  reglas: () => get<Reglas>('/api/reglas'),
  salud: () => get<Record<string, string>>('/api/salud')
}
