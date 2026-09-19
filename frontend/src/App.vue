<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api, SINTETICO, type RuntimeConfig, type SyncStatus, type VlmStatus } from './api'
import { irA, tab, tabs } from './nav'
import DashboardView from './views/DashboardView.vue'
import IngestView from './views/IngestView.vue'
import InvoicesView from './views/InvoicesView.vue'
import ReviewView from './views/ReviewView.vue'
import LogsView from './views/LogsView.vue'
import ConnectionSettings from './components/ConnectionSettings.vue'

// `confirmed` refleja el marcador `configured` persistido en la base de datos:
// si ya hay un modo guardado, no se fuerza el selector en cada arranque.
const confirmed = ref<boolean>(false)
const showSettings = ref<boolean>(false)
const configError = ref<string>('')

const currentConfig = ref<RuntimeConfig>({
  mode: 'standalone',
  sync_url: '',
  vlm_url: '',
  vlm_model: '',
  local_vlm_fallback: false,
  server_api_key: '',
  configured: false
})

const syncStatus = ref<SyncStatus | null>(null)
const vlmStatus = ref<VlmStatus | null>(null)
const vlmUnavailable = ref<boolean>(false)
let pollTimer: ReturnType<typeof setInterval> | undefined

async function fetchSyncStatus() {
  try {
    syncStatus.value = await api.syncStatus()
  } catch (error) {
    syncStatus.value = {
      state: 'error',
      pending: false,
      ok: false,
      error: String(error)
    }
  }
}

async function fetchVlmStatus() {
  try {
    vlmStatus.value = await api.vlmStatus()
    vlmUnavailable.value = false
  } catch {
    // No se conserva un estado "listo" obsoleto: se marca como no disponible.
    vlmStatus.value = null
    vlmUnavailable.value = true
  }
}

async function cargarConfigInicial() {
  try {
    const cfg = await api.getConfig()
    currentConfig.value = cfg
    confirmed.value = cfg.configured
    configError.value = ''
    await Promise.all([fetchSyncStatus(), fetchVlmStatus()])
  } catch (e: any) {
    // No se ocultan los fallos de carga con valores por defecto silenciosos.
    configError.value = `No se pudo cargar la configuración guardada: ${e?.message || e}`
  }
}

onMounted(() => {
  cargarConfigInicial()
  pollTimer = setInterval(() => {
    fetchSyncStatus()
    fetchVlmStatus().then(() => {
      const s = vlmStatus.value
      if (s && (s.state === 'downloading' || s.state === 'starting')) vigilarArranqueVlm()
    })
  }, 10_000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  if (vlmFastTimer) clearInterval(vlmFastTimer)
})

function onConfirmed(saved: RuntimeConfig) {
  currentConfig.value = saved
  confirmed.value = true
  showSettings.value = false
  configError.value = ''
  fetchSyncStatus()
  fetchVlmStatus()
}

function onManualSync() {
  fetchSyncStatus()
}

const vlmNotReady = computed(() => {
  if (!confirmed.value) return false
  if (vlmUnavailable.value) return true
  if (!vlmStatus.value) return false
  return vlmStatus.value.local_required && !vlmStatus.value.ready
})

const vlmBannerText = computed(() => {
  if (vlmUnavailable.value) return 'No se pudo consultar el estado del VLM local.'
  const s = vlmStatus.value
  if (!s) return ''
  if (s.state === 'downloading') return 'Descargando el modelo VLM local…'
  if (s.state === 'starting') return 'Iniciando el modelo VLM local…'
  if (s.state === 'error') return `El VLM local no está listo: ${s.error || s.detail || 'error'}`
  return 'El VLM local aún no está preparado.'
})

// El botón solo aparece cuando el VLM local es obligatorio (autónomo o
// respaldo), no está listo y no hay preparación en curso (idle/error).
// Nunca en modo remoto sin VLM local.
const vlmCanStart = computed(() => {
  const s = vlmStatus.value
  if (!s) return false
  return s.local_required && !s.ready && (s.state === 'idle' || s.state === 'error')
})

const vlmStarting = ref(false)
let vlmFastTimer: ReturnType<typeof setInterval> | undefined

/** Sondeo rápido mientras el modelo se descarga/arranca; se detiene al terminar. */
function vigilarArranqueVlm() {
  if (vlmFastTimer) return
  vlmFastTimer = setInterval(async () => {
    await fetchVlmStatus()
    const s = vlmStatus.value
    if (!s || (s.state !== 'downloading' && s.state !== 'starting')) {
      if (vlmFastTimer) clearInterval(vlmFastTimer)
      vlmFastTimer = undefined
    }
  }, 3_000)
}

async function startVlm() {
  if (vlmStarting.value) return
  vlmStarting.value = true
  try {
    vlmStatus.value = await api.vlmProvision()
    vlmUnavailable.value = false
    vigilarArranqueVlm()
  } catch {
    // El estado real se refleja en el siguiente sondeo; nunca se inventa "listo".
    await fetchVlmStatus()
  } finally {
    vlmStarting.value = false
  }
}

const statusBadgeText = computed(() => {
  if (SINTETICO) return 'sintético'
  if (!confirmed.value) return 'sin configurar'
  if (currentConfig.value.mode === 'server') {
    const s = syncStatus.value
    if (s?.state === 'error') return 'error sync'
    if (s?.state === 'syncing') return 'sincronizando...'
    if (s?.state === 'pending' || s?.pending) return 'sync pendiente'
    if (s?.state === 'synced') return 'servidor (sync ok)'
    return 'servidor'
  }
  if (vlmUnavailable.value) return 'VLM sin estado'
  if (vlmStatus.value && !vlmStatus.value.ready) {
    return vlmStatus.value.state === 'error' ? 'VLM error' : 'preparando VLM...'
  }
  return 'autónomo'
})

const statusBadgeTitle = computed(() => {
  if (SINTETICO) return 'Datos sintéticos de referencia (sin conexión real)'
  if (!confirmed.value) return 'Modo de ejecución pendiente de configurar'
  if (currentConfig.value.mode === 'server') {
    let msg = `Sincronizando con CouchDB: ${currentConfig.value.sync_url || '—'}`
    const s = syncStatus.value
    if (s?.error) {
      msg += `\nError: ${s.error}`
    } else if (s?.state) {
      msg += `\nEstado: ${s.state}`
    }
    return msg
  }
  if (vlmUnavailable.value) return 'No se pudo consultar el estado del VLM local'
  if (vlmStatus.value && !vlmStatus.value.ready) {
    return `VLM local: ${vlmStatus.value.state}${vlmStatus.value.error ? `\nError: ${vlmStatus.value.error}` : ''}`
  }
  return 'Modo autónomo (local con PouchDB independiente)'
})

const statusBadgeClass = computed(() => {
  if (SINTETICO) return 'badge-synthetic'
  if (!confirmed.value) return 'badge-unconfigured'
  if (currentConfig.value.mode === 'server') {
    const s = syncStatus.value
    if (s?.state === 'error') return 'badge-error'
    if (s?.state === 'pending' || s?.pending) return 'badge-server'
    if (s?.state === 'synced') return 'badge-ok'
    return 'badge-server'
  }
  if (vlmUnavailable.value) return 'badge-error'
  if (vlmStatus.value && !vlmStatus.value.ready) {
    return vlmStatus.value.state === 'error' ? 'badge-error' : 'badge-server'
  }
  return 'badge-standalone'
})

// --- Sync manual desde el topbar (misma acción que el botón de ConnectionSettings) ---
const syncingManual = ref(false)
const syncErrorMsg = ref('')
const syncOkMsg = ref('')

const syncConfigurado = computed(() =>
  confirmed.value
  && !SINTETICO
  && currentConfig.value.mode === 'server'
  && !!currentConfig.value.sync_url
)

// En curso si hay una petición manual activa o el sondeo ya ve "syncing".
const syncEnCurso = computed(() =>
  syncingManual.value || syncStatus.value?.state === 'syncing'
)

async function sincronizarAhora() {
  if (syncEnCurso.value || !syncConfigurado.value) return
  syncingManual.value = true
  syncErrorMsg.value = ''
  syncOkMsg.value = ''
  try {
    await api.sync()
    await fetchSyncStatus()
    syncOkMsg.value = 'Sincronización completada con éxito.'
  } catch (e: any) {
    await fetchSyncStatus()
    syncErrorMsg.value = `Error de sincronización: ${e?.message || e}`
  } finally {
    syncingManual.value = false
  }
}
</script>

<template>
  <header class="topbar">
    <nav v-if="confirmed">
      <button
        v-for="t in tabs"
        :key="t.id"
        class="tab"
        :class="{ active: tab === t.id }"
        @click="irA(t.id)"
      >
        {{ t.label }}
      </button>
    </nav>
    <div v-else class="startup-nav-title">
      <span class="app-title">filemaid</span>
    </div>

    <div class="topbar-right">
      <div
        class="modo"
        :class="statusBadgeClass"
        :title="statusBadgeTitle"
      >
        {{ statusBadgeText }}
      </div>
      <!-- Sync manual sin abrir el modal: misma acción que el botón de configuración -->
      <button
        v-if="syncConfigurado"
        type="button"
        class="sync-btn"
        :disabled="syncEnCurso"
        aria-label="Sincronizar ahora con el servidor"
        title="Sincronizar ahora con el servidor"
        @click="sincronizarAhora"
      >
        {{ syncEnCurso ? 'sincronizando...' : 'Sync ahora' }}
      </button>
      <span
        v-if="syncErrorMsg"
        class="sync-feedback"
        role="alert"
        aria-live="assertive"
      >{{ syncErrorMsg }}</span>

      <span
        v-else-if="syncOkMsg"
        class="sync-feedback"
        role="status"
        aria-live="polite"
      >{{ syncOkMsg }}</span>

      <!-- Botón de configuración siempre disponible -->
      <button
        type="button"
        class="config-btn"
        aria-label="Abrir configuración de conexión"
        title="Configuración de conexión y sincronización"
        @click="showSettings = true"
      >
        Configuración
      </button>

      <!-- Bloque reservado para el logo -->
      <div class="logo-box" title="filemaid">
        <img src="/logo.svg" alt="logo" />
      </div>
    </div>
  </header>

  <main>
    <!-- Sin modo persistido en la base de datos, mostramos el selector de inicio -->
    <div v-if="!confirmed" class="startup-container">
      <div v-if="configError" class="config-error" role="alert" aria-live="assertive">
        {{ configError }}
      </div>
      <ConnectionSettings
        :can-close="false"
        @confirmed="onConfirmed"
        @synced="onManualSync"
      />
    </div>

    <!-- Vistas operativas normales cuando el modo está confirmado -->
    <template v-else>
      <div v-if="vlmNotReady" class="vlm-banner" role="status" aria-live="polite">
        <span class="vlm-banner-text">{{ vlmBannerText }}</span>
        <button
          v-if="vlmCanStart"
          type="button"
          class="primary vlm-start"
          :disabled="vlmStarting"
          @click="startVlm"
        >
          Start VLM
        </button>
      </div>
      <DashboardView v-if="tab === 'dashboard'" />
      <IngestView v-else-if="tab === 'ingest'" />
      <InvoicesView v-else-if="tab === 'invoices'" />
      <ReviewView v-else-if="tab === 'review'" />
      <LogsView v-else />
    </template>
  </main>

  <!-- Modal/diálogo de configuración reabrible en cualquier momento -->
  <div
    v-if="confirmed && showSettings"
    class="modal-backdrop"
    role="dialog"
    aria-modal="true"
    aria-label="Configuración de ejecución"
    @click.self="showSettings = false"
  >
    <div class="modal-content">
      <ConnectionSettings
        :can-close="true"
        @close="showSettings = false"
        @confirmed="onConfirmed"
        @synced="onManualSync"
      />
    </div>
  </div>
</template>

<style scoped>
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--ink);
  color: var(--paper);
  border-bottom: 3px solid var(--gold);
  padding: 0 20px;
  gap: 16px;
}
nav { display: flex; gap: 2px; }
.startup-nav-title {
  display: flex;
  align-items: center;
  padding: 12px 0;
}
.app-title {
  font-family: var(--display);
  font-size: 17px;
  letter-spacing: 0.02em;
  color: var(--paper);
}
.app-title::after {
  content: '';
  display: inline-block;
  width: 7px;
  height: 7px;
  margin-left: 7px;
  background: var(--gold);
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.sync-btn {
  font-size: 12px;
  padding: 5px 11px;
  border: 1px solid var(--gold);
  background: transparent;
  color: var(--gold);
  border-radius: 0;
}
.sync-btn:hover { background: rgba(201, 161, 74, 0.14); }
.sync-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
  background: none;
}

.sync-feedback {
  font-size: 11px;
  max-width: 280px;
  white-space: normal;
  line-height: 1.3;
}
.sync-feedback[role='alert'] { color: #f0a79f; }
.sync-feedback[role='status'] { color: #9fd6c9; }

.tab {
  font-family: var(--display);
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  border: none;
  border-radius: 0;
  background: none;
  padding: 16px 13px 13px;
  color: rgba(244, 236, 216, 0.68);
  border-bottom: 3px solid transparent;
  margin-bottom: -3px;
}
.tab:hover { background: rgba(244, 236, 216, 0.08); color: var(--paper); }
.tab.active {
  color: var(--gold);
  border-bottom-color: var(--gold);
}

.config-btn {
  font-size: 12px;
  padding: 5px 11px;
  border: 1px solid rgba(244, 236, 216, 0.5);
  background: transparent;
  color: var(--paper);
  border-radius: 0;
}
.config-btn:hover { background: rgba(244, 236, 216, 0.12); }

.logo-box {
  width: 34px;
  height: 34px;
  border-radius: 0;
  background: var(--paper);
  border: 1px solid var(--ink);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  flex: none;
}
.logo-box img { width: 28px; height: 28px; object-fit: contain; }

.modo {
  font-family: var(--display);
  font-size: 10px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  border: 1px solid rgba(244, 236, 216, 0.5);
  border-radius: 0;
  padding: 3px 9px;
  background: transparent;
  color: var(--paper);
  white-space: nowrap;
}
.modo.badge-synthetic { color: var(--slate); border-color: var(--slate); }
.modo.badge-unconfigured { color: var(--gold); border-color: var(--gold); }
.modo.badge-server { color: var(--slate); border-color: var(--slate); }
.modo.badge-standalone { color: rgba(244, 236, 216, 0.8); }
.modo.badge-ok { color: #9fd6c9; border-color: #9fd6c9; }
.modo.badge-error { color: #f0a79f; border-color: #f0a79f; }

main {
  max-width: 1180px;
  margin: 0 auto;
  padding: 22px 20px 48px;
}

.startup-container {
  padding-top: 26px;
}

.config-error {
  max-width: 720px;
  margin: 0 auto 16px;
  padding: 10px 14px;
  border: 1px solid var(--red);
  border-left: 5px solid var(--red);
  font-size: 13px;
  background: var(--bad-bg);
  color: var(--bad-fg);
}

.vlm-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  flex-wrap: wrap;
  margin-bottom: 16px;
  padding: 10px 14px;
  border: 1px solid var(--ink);
  border-left: 5px solid var(--orange);
  background: var(--panel);
  color: var(--warn-fg);
  font-size: 13px;
}
.vlm-banner-text { flex: 1 1 320px; }
.vlm-start { flex: none; }

/* Modal backdrop & content */
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(42, 23, 15, 0.55);
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: 28px 20px;
  z-index: 1000;
  overflow-y: auto;
}

.modal-content {
  width: 100%;
  max-width: 720px;
}

@media (max-width: 720px) {
  .topbar {
    flex-wrap: wrap;
    padding: 0 12px;
  }
  nav {
    order: 2;
    flex: 1 1 100%;
    min-width: 0;
    overflow-x: auto;
  }
  .topbar-right {
    order: 1;
    flex: 1 1 100%;
    justify-content: space-between;
    padding: 8px 0;
  }
  .tab { padding: 12px 10px 10px; }
  main { padding: 16px 12px 40px; }
}
</style>
