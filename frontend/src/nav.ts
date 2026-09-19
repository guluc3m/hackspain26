// Estado de navegación compartido: pestaña activa y el filtro de factura
// con el que se quiere entrar en Logs (mismo sistema de filtro del finder).

import { ref } from 'vue'

export type Tab = 'dashboard' | 'invoices' | 'logs'

function tabInicial(): Tab {
  const h = window.location.hash.replace('#', '')
  return h === 'invoices' || h === 'logs' ? h : 'dashboard'
}

/** Pestaña activa (barra superior y vistas). */
export const tab = ref<Tab>(tabInicial())

/** Filtro por nombre de factura (file_id) preseleccionado en Logs. */
export const logsInvoice = ref('')

/** Pestañas de la barra superior. */
export const tabs: { id: Tab; label: string }[] = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'invoices', label: 'Invoices' },
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
