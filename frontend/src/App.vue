<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api, SINTETICO, type RuntimeConfig, type SyncStatus } from './api'
import { irA, tab, tabs } from './nav'
import DashboardView from './views/DashboardView.vue'
import InvoicesView from './views/InvoicesView.vue'
import LogsView from './views/LogsView.vue'
import ConnectionSettings from './components/ConnectionSettings.vue'

// Estado de modo seleccionado en esta sesión de la aplicación:
// En synthetic mode (MODE === 'syncth') se considera confirmado por defecto para que funcione autónomo de inmediato.
// En modo real, se requiere selección explícita del usuario en cada arranque (montaje de la app).
const confirmed = ref<boolean>(SINTETICO)
const showSettings = ref<boolean>(false)

const currentConfig = ref<RuntimeConfig>({
  mode: 'standalone',
  sync_url: '',
  vlm_url: '',
  vlm_model: ''
})

const syncStatus = ref<SyncStatus | null>(null)
let pollTimer: ReturnType<typeof setInterval> | undefined

async function fetchSyncStatus() {
  if (SINTETICO) return
  try {
    const s = await api.syncStatus()
    syncStatus.value = s
  } catch (error) {
    syncStatus.value = { ok: false, state: 'error', error: String(error) }
  }
}

async function cargarConfigInicial() {
  if (SINTETICO) {
    confirmed.value = true
    return
  }
  try {
    const cfg = await api.getConfig()
    currentConfig.value = cfg
    await fetchSyncStatus()
  } catch {
    // Si no se puede contactar todavía, mantener defaults
  }
}

onMounted(() => {
  cargarConfigInicial()
  pollTimer = setInterval(fetchSyncStatus, 10_000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})

function onConfirmed(saved: RuntimeConfig) {
  currentConfig.value = saved
  confirmed.value = true
  showSettings.value = false
  fetchSyncStatus()
}

function onManualSync() {
  fetchSyncStatus()
}

const statusBadgeText = computed(() => {
  if (SINTETICO) return 'sintético'
  if (!confirmed.value) return 'sin configurar'
  if (currentConfig.value.mode === 'server') {
    if (syncStatus.value?.state === 'syncing') return 'sincronizando...'
    if (syncStatus.value?.state === 'error') return 'error sync'
    if (syncStatus.value?.state === 'synced') return 'servidor (sync ok)'
    return 'servidor'
  }
  return 'autónomo'
})

const statusBadgeTitle = computed(() => {
  if (SINTETICO) return 'Datos sintéticos de referencia (sin conexión real)'
  if (!confirmed.value) return 'Modo de ejecución pendiente de seleccionar en esta sesión'
  if (currentConfig.value.mode === 'server') {
    let msg = `Sincronizando con CouchDB: ${currentConfig.value.sync_url || '—'}`
    if (syncStatus.value?.error) {
      msg += `\nError: ${syncStatus.value.error}`
    } else if (syncStatus.value?.state) {
      msg += `\nEstado: ${syncStatus.value.state}`
    }
    return msg
  }
  return 'Modo autónomo (local con PouchDB independiente)'
})

const statusBadgeClass = computed(() => {
  if (SINTETICO) return 'badge-synthetic'
  if (!confirmed.value) return 'badge-unconfigured'
  if (currentConfig.value.mode === 'server') {
    if (syncStatus.value?.state === 'error') return 'badge-error'
    if (syncStatus.value?.state === 'synced') return 'badge-ok'
    return 'badge-server'
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
      <div class="logo-box" title="albertitos">
        <img src="/logo.svg" alt="logo" />
      </div>
    </div>
  </header>

  <main>
    <!-- Si la aplicación aún no ha confirmado el modo de esta sesión, mostramos el selector de inicio -->
    <div v-if="!confirmed" class="startup-container">
      <ConnectionSettings
        :can-close="false"
        @confirmed="onConfirmed"
        @synced="onManualSync"
      />
    </div>

    <!-- Vistas operativas normales cuando el modo está confirmado -->
    <template v-else>
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
