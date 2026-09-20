// Estado de navegación compartido: pestaña activa y el filtro de factura
// con el que se quiere entrar en Logs (mismo sistema de filtro del finder).

import { ref } from 'vue'

export type Tab = 'dashboard' | 'ingest' | 'invoices' | 'review' | 'logs'

const TABS: Tab[] = ['dashboard', 'ingest', 'invoices', 'review', 'logs']

function tabInicial(): Tab {
  const h = window.location.hash.replace('#', '') as Tab
  return TABS.includes(h) ? h : 'dashboard'
}

/** Pestaña activa (barra superior y vistas). */
export const tab = ref<Tab>(tabInicial())

/** Filtro por nombre de factura (file_id) preseleccionado en Logs. */
export const logsInvoice = ref('')

/** Nº de revisiones pendientes (badge de la pestaña Revisión). */
export const pendientesRevision = ref(0)

/** Pestañas de la barra superior. */
export const tabs: { id: Tab; label: string }[] = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'ingest', label: 'Ingest' },
  { id: 'invoices', label: 'Invoices' },
  { id: 'review', label: 'Review' },
  { id: 'logs', label: 'Logs' }
]

export function irA(t: Tab): void {
  tab.value = t
  window.location.hash = t
}

/** Salta a Logs con el filtro de factura ya puesto. */
export function irALogsDe(invoiceName: string): void {
  logsInvoice.value = invoiceName
  irA('logs')
}
