<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import {
  api,
  SINTETICO,
  type RuntimeConfig,
  type RuntimeConfigInput,
  type VlmStatus
} from '../api'

const props = defineProps<{
  // Si canClose es true, se muestra botón para cerrar/cancelar
  canClose?: boolean
}>()

const emit = defineEmits<{
  (e: 'confirmed', config: RuntimeConfig): void
  (e: 'close'): void
  (e: 'synced'): void
}>()

const mode = ref<'standalone' | 'server'>('standalone')
const syncUrl = ref('')
const vlmUrl = ref('')
const vlmModel = ref('')
const localVlmFallback = ref(false)
const serverApiKey = ref('')

const loading = ref(true)
const saving = ref(false)
const syncing = ref(false)
const provisioning = ref(false)
const error = ref('')
const successMsg = ref('')
const savedConfig = ref<RuntimeConfig | null>(null)
const vlmStatus = ref<VlmStatus | null>(null)
const vlmUnavailable = ref(false)
let vlmTimer: ReturnType<typeof setInterval> | undefined

const isServerMode = computed(() => mode.value === 'server')
const canSync = computed(() => savedConfig.value?.mode === 'server'
  && mode.value === 'server' && syncUrl.value.trim() === savedConfig.value.sync_url)

const vlmReady = computed(() => vlmStatus.value?.ready === true)
const vlmBusy = computed(() => {
  const s = vlmStatus.value?.state
  return s === 'downloading' || s === 'starting'
})
// Autoridad: el modo guardado y confirmado, no el toggle sin guardar de la UI.
const localRequested = computed(() => {
  const s = savedConfig.value
  if (!s?.configured) return false
  return s.mode === 'standalone' || s.local_vlm_fallback
})

onMounted(async () => {
  loading.value = true
  error.value = ''
  try {
    const current = await api.getConfig()
    savedConfig.value = current
    aplicar(current)
    await cargarVlm()
  } catch (e: any) {
    if (!SINTETICO) {
      error.value = `No se pudo obtener la configuración actual: ${e?.message || e}`
    }
  } finally {
    loading.value = false
  }
  // Sondeo modesto mientras el panel está abierto: el progreso llega a
  // listo/error sin depender de reabrir el modal.
  vlmTimer = setInterval(cargarVlm, 5_000)
})

onUnmounted(() => {
  if (vlmTimer) clearInterval(vlmTimer)
})

/** Hidrata los campos del formulario desde la configuración persistida. */
function aplicar(cfg: RuntimeConfig) {
  mode.value = cfg.mode || 'standalone'
  syncUrl.value = cfg.sync_url || ''
  vlmUrl.value = cfg.vlm_url || ''
  vlmModel.value = cfg.vlm_model || ''
  localVlmFallback.value = cfg.local_vlm_fallback === true
  serverApiKey.value = cfg.server_api_key || ''
}

async function cargarVlm() {
  try {
    vlmStatus.value = await api.vlmStatus()
    vlmUnavailable.value = false
  } catch {
    // No se conserva un estado "listo" obsoleto.
    vlmStatus.value = null
    vlmUnavailable.value = true
  }
}

async function guardar() {
  if (saving.value || syncing.value) return
  error.value = ''
  successMsg.value = ''

  if (isServerMode.value) {
    if (!syncUrl.value.trim()) {
      error.value = 'El modo servidor requiere una URL completa de base de datos CouchDB (ej. http://couchdb:5984/facturas).'
      return
    }
    if (!vlmUrl.value.trim()) {
      error.value = 'El modo servidor requiere el endpoint VLM remoto (base OpenAI compatible terminada en /v1).'
      return
    }
    if (!serverApiKey.value.trim()) {
      error.value = 'El modo servidor requiere la clave de API del servidor.'
      return
    }
  }

  saving.value = true
  // En autónomo se limpian los campos remotos y el fallback: siempre local.
  const payload: RuntimeConfigInput = isServerMode.value
    ? {
        mode: 'server',
        sync_url: syncUrl.value.trim(),
        vlm_url: vlmUrl.value.trim(),
        vlm_model: vlmModel.value.trim(),
        local_vlm_fallback: localVlmFallback.value,
        server_api_key: serverApiKey.value.trim()
      }
    : {
        mode: 'standalone',
        sync_url: '',
        vlm_url: '',
        vlm_model: '',
        local_vlm_fallback: false,
        server_api_key: ''
      }

  try {
    const saved = await api.saveConfig(payload)
    savedConfig.value = saved
    aplicar(saved)
    successMsg.value = saved.mode === 'server'
      ? 'Configuración guardada. La sincronización CouchDB continúa en segundo plano.'
      : 'Modo autónomo guardado. El modelo VLM local se prepara en segundo plano.'
    emit('confirmed', saved)
    await cargarVlm()
  } catch (e: any) {
    // Se conservan los valores introducidos para que el usuario pueda reintentar.
    error.value = e?.message || String(e)
  } finally {
    saving.value = false
  }
}

async function sincronizarManual() {
  if (syncing.value || saving.value || !canSync.value) return
  error.value = ''
  successMsg.value = ''
  syncing.value = true

  try {
    await api.sync()
    successMsg.value = 'Sincronización completada con éxito.'
    emit('synced')
  } catch (e: any) {
    error.value = `Error de sincronización: ${e?.message || e}`
  } finally {
    syncing.value = false
  }
}

async function provisionar() {
  if (provisioning.value) return
  error.value = ''
  provisioning.value = true
  try {
    vlmStatus.value = await api.vlmProvision()
  } catch (e: any) {
    error.value = `No se pudo iniciar la preparación del VLM: ${e?.message || e}`
  } finally {
    provisioning.value = false
  }
}
</script>

<template>
  <div class="settings-card panel" role="region" aria-label="Configuración de conexión y ejecución">
    <div class="header-row">
      <div>
        <h2>Configuración de ejecución</h2>
        <p class="muted subtitle">
          Seleccione el modo de operación. En autónomo todo es local; en servidor se
          sincroniza con CouchDB remoto y usa un VLM remoto con respaldo local opcional.
        </p>
      </div>
      <button
        v-if="canClose"
        type="button"
        class="close-btn"
        aria-label="Cerrar ventana de configuración"
        @click="emit('close')"
      >
        Cerrar
      </button>
    </div>

    <div v-if="loading" class="loading-state muted" aria-live="polite">
      Cargando configuración actual...
    </div>

    <form v-else @submit.prevent="guardar">
      <!-- Selector de Modo -->
      <fieldset class="mode-selector">
        <legend class="section-legend">Modo de funcionamiento</legend>
        <div class="mode-options">
          <label class="mode-label" :class="{ selected: mode === 'standalone' }">
            <input
              v-model="mode"
              type="radio"
              name="mode"
              value="standalone"
              :disabled="saving || syncing"
            />
            <div class="mode-info">
              <span class="mode-title">Autónomo (Standalone)</span>
              <span class="mode-desc muted">
                Base local PouchDB (LevelDB) sin conexión remota. El modelo VLM local es
                obligatorio y se descarga/instala la primera vez.
              </span>
            </div>
          </label>

          <label class="mode-label" :class="{ selected: mode === 'server' }">
            <input
              v-model="mode"
              type="radio"
              name="mode"
              value="server"
              :disabled="saving || syncing"
            />
            <div class="mode-info">
              <span class="mode-title">Conectado a Servidor (Server)</span>
              <span class="mode-desc muted">
                Sincronización con CouchDB remoto y VLM remoto. El modelo local es un
                respaldo opcional.
              </span>
            </div>
          </label>
        </div>
      </fieldset>

      <!-- Autónomo: sin conexión remota; solo VLM local -->
      <fieldset v-if="!isServerMode" class="endpoints-fieldset">
        <legend class="section-legend">Procesamiento local</legend>
        <p class="offline-note muted">
          Sin conexión remota: no se contacta ningún servidor. La única descarga es el
          modelo VLM local, la primera vez que se prepara.
        </p>
      </fieldset>

      <!-- Servidor: CouchDB + VLM remoto + fallback local opcional -->
      <fieldset v-else class="endpoints-fieldset">
        <legend class="section-legend">Parámetros de conexión</legend>
        <p class="offline-note muted">
          El servidor combinado expone la base de datos y el VLM bajo el mismo host
          (p. ej. <span class="mono">/db/facturas</span> y <span class="mono">/v1</span>);
          indique cada URL explícitamente.
        </p>

        <div class="field-group">
          <label for="input-sync-url">
            URL Base de Datos CouchDB
            <span class="required" aria-hidden="true">*</span>
          </label>
          <input
            id="input-sync-url"
            v-model="syncUrl"
            type="text"
            placeholder="http://couchdb:5984/facturas"
            required
            :disabled="saving || syncing"
            aria-describedby="sync-url-help"
            autocomplete="off"
          />
          <span id="sync-url-help" class="help-text muted">
            URL HTTP(S) completa de la base de datos remota CouchDB (ej. http://couchdb:5984/facturas).
          </span>
        </div>

        <div class="field-group">
          <label for="input-vlm-url">
            Endpoint VLM remoto
            <span class="required" aria-hidden="true">*</span>
          </label>
          <input
            id="input-vlm-url"
            v-model="vlmUrl"
            type="text"
            placeholder="http://servidor:8001/v1"
            required
            :disabled="saving || syncing"
            aria-describedby="vlm-url-help"
            autocomplete="off"
          />
          <span id="vlm-url-help" class="help-text muted">
            Base OpenAI compatible terminada en /v1. Independiente de CouchDB (nunca se deduce de la URL de sync).
          </span>
        </div>

        <div class="field-group">
          <label for="input-vlm-model">Modelo VLM (Opcional)</label>
          <input
            id="input-vlm-model"
            v-model="vlmModel"
            type="text"
            placeholder="Identificador del modelo configurado en el servidor"
            :disabled="saving || syncing"
            aria-describedby="vlm-model-help"
            autocomplete="off"
          />
          <span id="vlm-model-help" class="help-text muted">
            Identificador del modelo de visión. En blanco usa el modelo por defecto del servicio.
          </span>
        </div>

        <div class="field-group">
          <label for="input-server-api-key">API key</label>
          <input
            id="input-server-api-key"
            v-model="serverApiKey"
            type="password"
            placeholder="clave de API del servidor"
            :disabled="saving || syncing"
            aria-describedby="server-api-key-help"
            autocomplete="off"
          />
          <span id="server-api-key-help" class="help-text muted">
            Clave de API del servidor (base de datos y VLM). Se guarda localmente y
            nunca se muestra en la interfaz ni en los registros.
          </span>
        </div>

        <label class="fallback-toggle">
          <input
            v-model="localVlmFallback"
            type="checkbox"
            :disabled="saving || syncing"
          />
          <span>
            Usar modelo VLM local de respaldo
            <span class="help-text muted">
              Si el VLM remoto no responde, se prepara y usa un modelo local.
            </span>
          </span>
        </label>
      </fieldset>

      <!-- Estado del VLM local -->
      <div
        v-if="vlmStatus || vlmUnavailable"
        class="vlm-status"
        :class="{
          'vlm-ready': vlmReady,
          'vlm-busy': vlmBusy,
          'vlm-error': vlmUnavailable || vlmStatus?.state === 'error'
        }"
        role="status"
        aria-live="polite"
      >
        <div class="vlm-status-head">
          <strong>VLM local:</strong>
          <span v-if="vlmUnavailable">estado no disponible</span>
          <span v-else-if="vlmBusy">preparando modelo…</span>
          <span v-else-if="vlmReady">listo</span>
          <span v-else-if="vlmStatus?.state === 'error'">error</span>
          <span v-else-if="vlmStatus?.state === 'remote-only'">no requerido (VLM remoto)</span>
          <span v-else>pendiente</span>
        </div>
        <p v-if="vlmUnavailable" class="help-text vlm-error-text">
          No se pudo consultar el estado del VLM local.
        </p>
        <template v-else-if="vlmStatus">
          <p v-if="!vlmReady && vlmStatus.local_required" class="help-text muted">
            Descargado: {{ vlmStatus.downloaded ? 'sí' : 'no' }} · En ejecución: {{ vlmStatus.running ? 'sí' : 'no' }}
          </p>
          <p v-if="vlmStatus.detail" class="help-text muted">{{ vlmStatus.detail }}</p>
          <p v-if="vlmStatus.error" class="help-text vlm-error-text">{{ vlmStatus.error }}</p>
        </template>
        <button
          v-if="localRequested && !vlmReady && !vlmBusy"
          type="button"
          class="retry-btn"
          :disabled="provisioning"
          @click="provisionar"
        >
          {{ provisioning ? 'Iniciando…' : 'Start VLM' }}
        </button>
      </div>

      <!-- Mensajes de estado -->
      <div v-if="error" class="message-box error" role="alert" aria-live="assertive">
        <strong>Error:</strong> {{ error }}
      </div>
      <div v-if="successMsg" class="message-box success" role="status" aria-live="polite">
        {{ successMsg }}
      </div>

      <!-- Acciones -->
      <div class="actions-row">
        <div class="left-actions">
          <button
            v-if="isServerMode"
            type="button"
            class="sync-btn"
            :disabled="saving || syncing || !canSync"
            @click="sincronizarManual"
          >
            {{ syncing ? 'Sincronizando...' : 'Sincronizar ahora' }}
            <span v-if="!canSync"> (guarde primero la configuración)</span>
          </button>
        </div>

        <div class="right-actions">
          <button
            v-if="canClose"
            type="button"
            class="cancel-btn"
            :disabled="saving || syncing"
            @click="emit('close')"
          >
            Cancelar
          </button>
          <button
            type="submit"
            class="primary confirm-btn"
            :disabled="saving || syncing"
          >
            {{ saving ? 'Guardando...' : (isServerMode ? 'Guardar y conectar' : 'Confirmar modo local') }}
          </button>
        </div>
      </div>
    </form>
  </div>
</template>

<style scoped>
.settings-card {
  max-width: 680px;
  margin: 0 auto;
  background: var(--panel);
}

.header-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
}

.subtitle {
  margin-top: 4px;
  font-size: 13px;
}

.close-btn {
  font-size: 16px;
  padding: 4px 8px;
  border: none;
  background: none;
  color: var(--muted);
}
.close-btn:hover {
  color: var(--text);
  background: var(--sand);
}

.section-legend {
  font-weight: 600;
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--muted);
  margin-bottom: 10px;
  padding: 0;
}

fieldset {
  border: none;
  padding: 0;
  margin: 0 0 20px 0;
}

.mode-options {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.mode-label {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px;
  border: 1px solid var(--ink);
  border-left: 5px solid var(--border-soft);
  border-radius: 0;
  cursor: pointer;
  background: var(--panel);
  transition: border-color 0.15s, background 0.15s;
}

.mode-label:hover {
  background: var(--sand);
}

.mode-label.selected {
  border-left-color: var(--gold);
  background: var(--panel);
}

.mode-label input[type="radio"] {
  margin-top: 3px;
  cursor: pointer;
}

.mode-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.mode-title {
  font-weight: 600;
  font-size: 14px;
}

.mode-desc {
  font-size: 12px;
  line-height: 1.4;
}

.endpoints-fieldset {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding-top: 8px;
  border-top: 1px solid var(--border-soft);
}

.offline-note {
  font-size: 12px;
  line-height: 1.4;
}

.field-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.field-group label {
  font-weight: 500;
  font-size: 13px;
}

.field-group input {
  padding: 8px 10px;
  font-size: 13px;
}

.required {
  color: var(--bad-fg);
  margin-left: 2px;
}

.help-text {
  font-size: 11px;
  line-height: 1.3;
}

.fallback-toggle {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 13px;
  cursor: pointer;
}

.fallback-toggle input[type="checkbox"] {
  margin-top: 2px;
  cursor: pointer;
}

.fallback-toggle .help-text {
  display: block;
}

.vlm-status {
  border: 1px solid var(--ink);
  border-left: 5px solid var(--border-soft);
  border-radius: 0;
  padding: 10px 14px;
  margin-bottom: 16px;
  font-size: 13px;
  background: var(--panel);
}

.vlm-status-head {
  display: flex;
  gap: 6px;
  align-items: baseline;
}

.vlm-status.vlm-ready {
  border-left-color: var(--ok-fg);
  background: var(--ok-bg);
}

.vlm-status.vlm-busy {
  border-left-color: var(--warn-fg);
  background: var(--warn-bg);
}

.vlm-status.vlm-error {
  border-left-color: var(--bad-fg);
  background: var(--bad-bg);
}

.vlm-error-text {
  color: var(--bad-fg);
}

.retry-btn {
  margin-top: 8px;
  font-size: 12px;
  padding: 4px 10px;
}

.message-box {
  padding: 10px 14px;
  border-radius: 0;
  font-size: 13px;
  margin-bottom: 16px;
}

.message-box.error {
  background: var(--bad-bg);
  color: var(--bad-fg);
  border: 1px solid var(--bad-fg);
}

.message-box.success {
  background: var(--ok-bg);
  color: var(--ok-fg);
  border: 1px solid var(--ok-fg);
}

.actions-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
}

.left-actions, .right-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.loading-state {
  padding: 30px 0;
  text-align: center;
}
</style>
