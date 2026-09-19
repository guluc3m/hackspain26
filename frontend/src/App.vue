<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api, SINTETICO, type RuntimeConfig, type SyncStatus, type VlmStatus } from './api'
import { irA, tab, tabs } from './nav'
import DashboardView from './views/DashboardView.vue'
import InvoicesView from './views/InvoicesView.vue'
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
    fetchVlmStatus()
  }, 10_000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
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
        {{ vlmBannerText }}
      </div>
      <DashboardView v-if="tab === 'dashboard'" />
      <InvoicesView v-else-if="tab === 'invoices'" />
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
  background: var(--panel);
  border-bottom: 1px solid var(--border);
  padding: 0 20px;
}
nav { display: flex; gap: 4px; }
.startup-nav-title {
  display: flex;
  align-items: center;
  padding: 14px 0;
}
.app-title {
  font-weight: 700;
  font-size: 16px;
  letter-spacing: -0.02em;
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.tab {
  border: none;
  border-radius: 0;
  background: none;
  padding: 16px 12px 14px;
  font-size: 15px;
  color: var(--muted);
  border-bottom: 2px solid transparent;
}
.tab:hover { background: none; color: var(--text); }
.tab.active {
  color: var(--text);
  font-weight: 600;
  border-bottom-color: var(--accent);
}

.config-btn {
  font-size: 13px;
  padding: 4px 10px;
  border: 1px solid var(--border);
  background: var(--panel);
  color: var(--text);
  border-radius: 4px;
}
.config-btn:hover {
  background: #fafaf9;
}

.logo-box {
  width: 36px;
  height: 36px;
  border-radius: 6px;
  background: #1c3144;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  flex: none;
}
.logo-box img { width: 30px; height: 30px; object-fit: contain; }

.modo {
  font-size: 12px;
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 2px 10px;
  background: var(--panel);
  color: var(--muted);
}
.modo.badge-synthetic {
  color: var(--muted);
}
.modo.badge-unconfigured {
  color: var(--warn-fg);
  border-color: var(--warn-fg);
  background: var(--warn-bg);
}
.modo.badge-server {
  color: var(--accent);
  border-color: var(--accent);
}
.modo.badge-standalone {
  color: var(--muted);
  border-color: var(--border);
}
.modo.badge-ok {
  color: var(--ok-fg);
  border-color: var(--ok-fg);
  background: var(--ok-bg);
}
.modo.badge-error {
  color: var(--bad-fg);
  border-color: var(--bad-fg);
  background: var(--bad-bg);
}

main {
  max-width: 1100px;
  margin: 0 auto;
  padding: 20px;
}

.startup-container {
  padding-top: 30px;
}

.config-error {
  max-width: 680px;
  margin: 0 auto 16px;
  padding: 10px 14px;
  border-radius: 4px;
  font-size: 13px;
  background: var(--bad-bg);
  color: var(--bad-fg);
  border: 1px solid var(--bad-fg);
}

.vlm-banner {
  margin-bottom: 16px;
  padding: 10px 14px;
  border-radius: 4px;
  font-size: 13px;
  background: var(--warn-bg);
  color: var(--warn-fg);
  border: 1px solid var(--warn-fg);
}

/* Modal backdrop & content */
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  z-index: 1000;
  overflow-y: auto;
}

.modal-content {
  width: 100%;
  max-width: 680px;
}
</style>
