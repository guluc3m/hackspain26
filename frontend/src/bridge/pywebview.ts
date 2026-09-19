// Puente con la ventana nativa (pywebview). window.pywebview.api lo inyecta
// el lado Python (src/filemaid/desktop/app.py).
//
// La conexión real de datos usa el mismo FastAPI local que el navegador; el
// puente solo expone lo que NO puede existir en un navegador: la vigilancia de
// una carpeta del sistema y el selector nativo de carpetas. En un navegador
// normal `window.pywebview` no existe y la sección de vigilancia no se ofrece.

/** Estado de la vigilancia de carpeta (solo app de escritorio). */
export interface EstadoVigilancia {
  enabled: boolean
  folder: string
  running: boolean
  error: string
  processed: number
  pending: number
  notifications: { available: boolean; detail: string }
}

export interface PywebviewApi {
  ping(): Promise<string>
  /** Selector nativo de carpeta; `path` null si se cancela. */
  elegir_carpeta(): Promise<{ path: string | null; error: string }>
  vigilancia_estado(): Promise<EstadoVigilancia>
  vigilancia_configurar(folder: string, enabled: boolean): Promise<EstadoVigilancia>
  vigilancia_escanear(): Promise<EstadoVigilancia>
}

declare global {
  interface Window {
    pywebview?: { api: PywebviewApi }
  }
}

/** API del puente si existe (nunca en un navegador normal). */
export function puente(): PywebviewApi | undefined {
  return typeof window !== 'undefined' ? window.pywebview?.api : undefined
}

export function puenteDisponible(): boolean {
  return puente() !== undefined
}

/**
 * Vigilancia disponible: exige el puente nativo Y el método de estado. En un
 * navegador no se ofrece nunca (no se puede vigilar un sistema de ficheros).
 */
export function vigilanciaDisponible(): boolean {
  return typeof puente()?.vigilancia_estado === 'function'
}

/** Espera al evento `pywebviewready` (el puente se inyecta tras cargar). */
export function esperarPuente(timeoutMs = 4000): Promise<boolean> {
  if (vigilanciaDisponible()) return Promise.resolve(true)
  if (typeof window === 'undefined') return Promise.resolve(false)
  return new Promise<boolean>((resolve) => {
    const listo = () => {
      window.removeEventListener('pywebviewready', listo)
      resolve(vigilanciaDisponible())
    }
    window.addEventListener('pywebviewready', listo)
    setTimeout(() => {
      window.removeEventListener('pywebviewready', listo)
      resolve(vigilanciaDisponible())
    }, timeoutMs)
  })
}

/** Comprueba el puente con la ventana; null fuera de pywebview. */
export async function pingPuente(): Promise<string | null> {
  return (await puente()?.ping()) ?? null
}

/** Selector nativo de carpeta (solo app de escritorio). */
export async function elegirCarpeta(): Promise<{ path: string | null; error: string }> {
  const api = puente()
  if (!api) return { path: null, error: 'solo app de escritorio' }
  return api.elegir_carpeta()
}

export async function vigilanciaEstado(): Promise<EstadoVigilancia> {
  const api = puente()
  if (!api) throw new Error('vigilancia no disponible fuera de la app de escritorio')
  return api.vigilancia_estado()
}

export async function vigilanciaConfigurar(folder: string, enabled: boolean): Promise<EstadoVigilancia> {
  const api = puente()
  if (!api) throw new Error('vigilancia no disponible fuera de la app de escritorio')
  return api.vigilancia_configurar(folder, enabled)
}

export async function vigilanciaEscanear(): Promise<EstadoVigilancia> {
  const api = puente()
  if (!api) throw new Error('vigilancia no disponible fuera de la app de escritorio')
  return api.vigilancia_escanear()
}
