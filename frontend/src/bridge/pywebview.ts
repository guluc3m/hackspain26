// Puente con la ventana nativa (pywebview). window.pywebview.api lo inyecta
// el lado Python (src/filemaid/desktop/app.py), que puede llamar a los dos
// motores de la arquitectura (engines.extraction / engines.decision).
//
// Las llamadas a los motores están SIN DEFINIR en el lado Python: este módulo
// solo tipa la superficie. Los datos de la UI siguen siendo la referencia
// sintética (src/mock/data.ts), dentro o fuera de la ventana.

export interface PywebviewApi {
  ping(): Promise<string>
  /** PDF -> campos (motor de extracción). Sin definir en Python. */
  extraer(fileId: string): Promise<unknown>
  /** Campos -> decisión (motor de decisión). Sin definir en Python. */
  decidir(invoiceId: string): Promise<unknown>
}

declare global {
  interface Window {
    pywebview?: { api: PywebviewApi }
  }
}

export function puenteDisponible(): boolean {
  return typeof window !== 'undefined' && window.pywebview !== undefined
}

/** Comprueba el puente con la ventana; null fuera de pywebview. */
export async function pingPuente(): Promise<string | null> {
  return (await window.pywebview?.api.ping()) ?? null
}

/** Llamada al motor de extracción. Sin definir aún en el lado Python. */
export async function extraerEnPuente(fileId: string): Promise<unknown> {
  return window.pywebview?.api.extraer(fileId)
}

/** Llamada al motor de decisión. Sin definir aún en el lado Python. */
export async function decidirEnPuente(invoiceId: string): Promise<unknown> {
  return window.pywebview?.api.decidir(invoiceId)
}
