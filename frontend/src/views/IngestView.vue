<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api, type IngestRejected, type JobStatus } from '../api'
import { irA } from '../nav'
import {
  elegirCarpeta,
  esperarPuente,
  vigilanciaConfigurar,
  vigilanciaDisponible,
  vigilanciaEscanear,
  vigilanciaEstado,
  type EstadoVigilancia
} from '../bridge/pywebview'

// ---- subida de ficheros ---------------------------------------------------

interface Seleccion {
  relPath: string
  file: File
}

const SUFIJOS = ['.pdf', '.png', '.jpg', '.jpeg']
const MAX_BYTES = 64 * 1024 * 1024

const seleccion = ref<Seleccion[]>([])
const rechazadosCliente = ref<IngestRejected[]>([])
const rechazadosServidor = ref<IngestRejected[]>([])
const subiendo = ref(false)
const error = ref('')
const job = ref<JobStatus | null>(null)
let jobTimer: ReturnType<typeof setInterval> | undefined

function aceptarArchivos(list: FileList | null, conRuta: boolean) {
  if (!list) return
  const validos: Seleccion[] = []
  const rechazados: IngestRejected[] = []
  const vistos = new Set<string>()
  for (const file of Array.from(list)) {
    const relPath = conRuta && file.webkitRelativePath ? file.webkitRelativePath : file.name
    const ext = relPath.slice(relPath.lastIndexOf('.')).toLowerCase()
    if (!SUFIJOS.includes(ext)) {
      rechazados.push({ rel_path: relPath, reason: 'extensión no soportada' })
      continue
    }
    if (file.size > MAX_BYTES) {
      rechazados.push({ rel_path: relPath, reason: 'fichero mayor de 64 MiB' })
      continue
    }
    if (vistos.has(relPath)) {
      rechazados.push({ rel_path: relPath, reason: 'ruta relativa duplicada' })
      continue
    }
    vistos.add(relPath)
    validos.push({ relPath, file })
  }
  seleccion.value = validos
  rechazadosCliente.value = rechazados
  rechazadosServidor.value = []
  job.value = null
  error.value = ''
}

function onCarpeta(e: Event) {
  aceptarArchivos((e.target as HTMLInputElement).files, true)
}

function onArchivos(e: Event) {
  aceptarArchivos((e.target as HTMLInputElement).files, false)
}

function vigilarJob(jobId: string) {
  if (jobTimer) clearInterval(jobTimer)
  jobTimer = setInterval(async () => {
    try {
      const j = await api.job(jobId)
      job.value = j
      if (j.state === 'complete' || j.state === 'failed') {
        if (jobTimer) clearInterval(jobTimer)
        jobTimer = undefined
      }
    } catch (e) {
      error.value = String(e)
      if (jobTimer) clearInterval(jobTimer)
      jobTimer = undefined
    }
  }, 1500)
}

async function subir() {
  if (subiendo.value || seleccion.value.length === 0) return
  subiendo.value = true
  error.value = ''
  rechazadosServidor.value = []
  try {
    const res = await api.ingest(seleccion.value.map((s) => ({ relPath: s.relPath, file: s.file })))
    rechazadosServidor.value = res.rejected
    job.value = await api.job(res.job_id)
    vigilarJob(res.job_id)
  } catch (e) {
    error.value = String(e)
  } finally {
    subiendo.value = false
  }
}

const progreso = computed(() => {
  const c = job.value?.counts
  if (!c || c.total === 0) return 0
  return Math.round(((c.done + c.error) / c.total) * 100)
})

// destino inteligente al completar: si hay escaladas, la cola de revisión
const escaladas = computed(() =>
  job.value?.state === 'complete' ? job.value.items.filter((it) => it.result === 'ESCALAR').length : 0
)

function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KiB`
  return `${(n / (1024 * 1024)).toFixed(1)} MiB`
}

// ---- vigilancia de carpeta (solo app de escritorio) -----------------------

const nativo = ref(false)
const watcher = ref<EstadoVigilancia | null>(null)
const watcherError = ref('')
const watcherBusy = ref(false)
let watcherTimer: ReturnType<typeof setInterval> | undefined

async function cargarWatcher() {
  if (!vigilanciaDisponible()) return
  try {
    watcher.value = await vigilanciaEstado()
    watcherError.value = ''
  } catch (e) {
    watcherError.value = String(e)
  }
}

async function elegirYActivar() {
  if (watcherBusy.value) return
  watcherBusy.value = true
  watcherError.value = ''
  try {
    const { path, error: err } = await elegirCarpeta()
    if (err) watcherError.value = err
    if (path) watcher.value = await vigilanciaConfigurar(path, true)
  } catch (e) {
    watcherError.value = String(e)
  } finally {
    watcherBusy.value = false
  }
}

async function alternarVigilancia() {
  if (watcherBusy.value || !watcher.value) return
  watcherBusy.value = true
  watcherError.value = ''
  try {
    watcher.value = await vigilanciaConfigurar(watcher.value.folder, !watcher.value.enabled)
  } catch (e) {
    watcherError.value = String(e)
  } finally {
    watcherBusy.value = false
  }
}

async function escanearAhora() {
  if (watcherBusy.value) return
  watcherBusy.value = true
  watcherError.value = ''
  try {
    watcher.value = await vigilanciaEscanear()
  } catch (e) {
    watcherError.value = String(e)
  } finally {
    watcherBusy.value = false
  }
}

onMounted(async () => {
  nativo.value = await esperarPuente()
  if (nativo.value) {
    await cargarWatcher()
    watcherTimer = setInterval(cargarWatcher, 5000)
  }
})

onUnmounted(() => {
  if (jobTimer) clearInterval(jobTimer)
  if (watcherTimer) clearInterval(watcherTimer)
})
</script>

<template>
  <h2>Ingesta</h2>
  <p class="muted intro">
    Sube una carpeta de facturas: el backend valida cada fichero, lo procesa y la
    UI refleja el estado real de la base de datos.
  </p>

  <section class="panel">
    <h3>Subir ficheros</h3>
    <div class="toolbar">
      <label class="file-btn">
        Seleccionar carpeta
        <input
          type="file"
          webkitdirectory
          multiple
          :disabled="subiendo"
          @change="onCarpeta"
        />
      </label>
      <label class="file-btn">
        Seleccionar ficheros
        <input
          type="file"
          multiple
          accept=".pdf,.png,.jpg,.jpeg"
          :disabled="subiendo"
          @change="onArchivos"
        />
      </label>
      <button
        type="button"
        class="primary"
        :disabled="subiendo || seleccion.length === 0"
        @click="subir"
      >
        {{ subiendo ? 'Subiendo…' : `Subir ${seleccion.length} fichero(s)` }}
      </button>
    </div>

    <p v-if="error" class="error" role="alert">{{ error }}</p>

    <div v-if="seleccion.length" class="lista-validos">
      <p class="muted">{{ seleccion.length }} fichero(s) válidos listos para subir:</p>
      <ul>
        <li v-for="s in seleccion" :key="s.relPath">
          <span class="mono">{{ s.relPath }}</span>
          <span class="muted"> · {{ fmtBytes(s.file.size) }}</span>
        </li>
      </ul>
    </div>

    <div v-if="rechazadosCliente.length" class="rechazos">
      <p class="muted">{{ rechazadosCliente.length }} fichero(s) descartados antes de subir:</p>
      <ul>
        <li v-for="r in rechazadosCliente" :key="r.rel_path">
          <span class="mono">{{ r.rel_path }}</span> — {{ r.reason }}
        </li>
      </ul>
    </div>

    <div v-if="rechazadosServidor.length" class="rechazos">
      <p class="muted">{{ rechazadosServidor.length }} fichero(s) rechazados por el backend:</p>
      <ul>
        <li v-for="r in rechazadosServidor" :key="r.rel_path">
          <span class="mono">{{ r.rel_path }}</span> — {{ r.reason }}
        </li>
      </ul>
    </div>
  </section>

  <section v-if="job" class="panel job">
    <div class="job-head">
      <h3>Procesamiento</h3>
      <span class="badge" :class="job.state === 'failed' ? 'NO_PAGAR' : job.state === 'complete' ? 'PAGAR' : 'ESCALAR'">
        {{ job.state }}
      </span>
    </div>
    <div class="bar" role="progressbar" :aria-valuenow="progreso" aria-valuemin="0" aria-valuemax="100">
      <span :style="{ width: progreso + '%' }"></span>
    </div>
    <p class="muted">
      {{ job.counts.done }} hechas · {{ job.counts.pending }} pendientes ·
      {{ job.counts.error }} con error · total {{ job.counts.total }}
    </p>

    <table>
      <thead>
        <tr><th>Fichero</th><th>Estado</th><th>Resultado</th><th>Error</th></tr>
      </thead>
      <tbody>
        <tr v-for="it in job.items" :key="it.file_key">
          <td class="mono">{{ it.file_id }}</td>
          <td>{{ it.status }}</td>
          <td>
            <span v-if="it.result" class="badge" :class="it.result">{{ it.result }}</span>
            <span v-else class="muted">—</span>
          </td>
          <td class="error">{{ it.error ?? '' }}</td>
        </tr>
      </tbody>
    </table>

    <div v-if="job.state === 'complete'" class="job-done">
      <button v-if="escaladas > 0" type="button" class="primary" @click="irA('review')">
        Revisar {{ escaladas }} escalada(s)
      </button>
      <button v-else type="button" class="primary" @click="irA('invoices')">Ver facturas</button>
    </div>
  </section>

  <section v-if="nativo" class="panel watcher">
    <h3>Vigilancia de carpeta</h3>
    <p class="muted">
      Solo en la app de escritorio: vigila una carpeta local y procesa los ficheros
      nuevos. Minimizar la ventana mantiene la vigilancia; cerrarla la detiene.
    </p>

    <p v-if="watcherError" class="error" role="alert">{{ watcherError }}</p>

    <template v-if="watcher">
      <dl class="watcher-meta">
        <dt>Carpeta</dt>
        <dd class="mono">{{ watcher.folder || '—' }}</dd>
        <dt>Estado</dt>
        <dd>
          <span class="badge" :class="watcher.enabled ? 'PASS' : 'pendiente'">
            {{ watcher.enabled ? 'activa' : 'detenida' }}
          </span>
          <span v-if="watcher.running" class="muted"> · en ejecución</span>
        </dd>
        <dt>Procesadas</dt>
        <dd>
          {{ watcher.processed }} · {{ watcher.pending }} pendientes
          <span v-if="watcher.last_scan > 0" class="muted">
            · último sondeo {{ new Date(watcher.last_scan * 1000).toLocaleTimeString() }}
          </span>
        </dd>
        <dt>Notificaciones</dt>
        <dd>
          {{ watcher.notifications.available ? 'disponibles' : 'no disponibles' }}
          <span class="muted"> · {{ watcher.notifications.detail }}</span>
        </dd>
      </dl>

      <p v-if="watcher.error" class="error" role="alert">{{ watcher.error }}</p>

      <div class="toolbar">
        <button type="button" :disabled="watcherBusy" @click="elegirYActivar">
          {{ watcher.folder ? 'Cambiar carpeta' : 'Elegir carpeta' }}
        </button>
        <button
          type="button"
          class="primary"
          :disabled="watcherBusy || !watcher.folder"
          @click="alternarVigilancia"
        >
          {{ watcher.enabled ? 'Detener vigilancia' : 'Activar vigilancia' }}
        </button>
        <button
          type="button"
          :disabled="watcherBusy || !watcher.enabled"
          @click="escanearAhora"
        >
          Escanear ahora
        </button>
      </div>
    </template>
    <p v-else class="muted">Cargando estado de la vigilancia…</p>
  </section>
</template>

<style scoped>
.intro { margin: 0 0 12px; max-width: 760px; }
.panel { margin-bottom: 14px; }
.job { overflow-x: auto; }

.file-btn {
  display: inline-block;
  border: 1px solid var(--ink);
  background: var(--panel);
  padding: 5px 12px;
  cursor: pointer;
  font-size: 14px;
}
.file-btn:hover { background: var(--sand); }
.file-btn input { display: none; }

.lista-validos, .rechazos { margin-top: 12px; }
.lista-validos ul, .rechazos ul {
  margin: 4px 0 0;
  padding-left: 18px;
  max-height: 220px;
  overflow: auto;
}
.lista-validos li, .rechazos li { overflow-wrap: anywhere; }
.rechazos { color: var(--bad-fg); }

.job-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.bar {
  height: 10px;
  border: 1px solid var(--ink);
  background: var(--sand);
  margin: 8px 0;
}
.bar span { display: block; height: 100%; background: var(--gold); }
.job-done { margin-top: 12px; }

.watcher-meta {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 4px 14px;
  margin: 10px 0;
}
.watcher-meta dt { color: var(--muted); }
.watcher-meta dd { margin: 0; overflow-wrap: anywhere; }
</style>
