<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api, SINTETICO, type RuntimeConfig } from '../api'

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

const loading = ref(true)
const saving = ref(false)
const syncing = ref(false)
const error = ref('')
const successMsg = ref('')
const savedConfig = ref<RuntimeConfig | null>(null)
const canSync = computed(() => savedConfig.value?.mode === 'server'
  && mode.value === 'server' && syncUrl.value.trim() === savedConfig.value.sync_url)

const isServerMode = computed(() => mode.value === 'server')

onMounted(async () => {
  loading.value = true
  error.value = ''
  try {
    const current = await api.getConfig()
    savedConfig.value = current
    mode.value = current.mode || 'standalone'
    syncUrl.value = current.sync_url || ''
    vlmUrl.value = current.vlm_url || ''
    vlmModel.value = current.vlm_model || ''
  } catch (e: any) {
    if (!SINTETICO) {
      error.value = `No se pudo obtener la configuración actual: ${e?.message || e}`
    }
  } finally {
    loading.value = false
  }
})

async function guardar() {
  if (saving.value || syncing.value) return
  error.value = ''
  successMsg.value = ''

  if (isServerMode.value && !syncUrl.value.trim()) {
    error.value = 'El modo servidor requiere una URL completa de base de datos CouchDB (ej. http://couchdb:5984/facturas).'
    return
  }

  saving.value = true
  const payload: RuntimeConfig = {
    mode: mode.value,
    sync_url: syncUrl.value.trim(),
    vlm_url: vlmUrl.value.trim(),
    vlm_model: vlmModel.value.trim()
  }

  try {
    const saved = await api.saveConfig(payload)
    savedConfig.value = saved
    successMsg.value = mode.value === 'server'
      ? 'Configuración de sincronización CouchDB guardada correctamente.'
      : 'Modo autónomo (local) configurado correctamente.'
    emit('confirmed', saved)
  } catch (e: any) {
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
</script>

<template>
  <div class="settings-card panel" role="region" aria-label="Configuración de conexión y ejecución">
    <div class="header-row">
      <div>
        <h2>Configuración de ejecución</h2>
        <p class="muted subtitle">
          Seleccione el modo de operación para persistencia PouchDB local y sincronización con CouchDB remoto o escalado VLM independiente.
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
                Base local PouchDB (LevelDB) independiente sin dependencias externas. Procesamiento VLM local o remoto independiente sin sincronización con CouchDB.
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
                Replicación bidireccional nativa entre PouchDB local y base remota CouchDB. El cliente no requiere CouchDB local. VLM independiente y opcional.
              </span>
            </div>
          </label>
        </div>
      </fieldset>

      <!-- Campos de Configuración de Servidor / VLM -->
      <fieldset class="endpoints-fieldset">
        <legend class="section-legend">Parámetros de conexión</legend>

        <div class="field-group">
          <label for="input-sync-url">
            URL Base de Datos CouchDB
            <span v-if="isServerMode" class="required" aria-hidden="true">*</span>
          </label>
          <input
            id="input-sync-url"
            v-model="syncUrl"
            type="text"
            placeholder="http://couchdb:5984/facturas"
            :required="isServerMode"
            :disabled="saving || syncing"
            aria-describedby="sync-url-help"
            autocomplete="off"
          />
          <span id="sync-url-help" class="help-text muted">
            URL HTTP(S) completa de la base de datos remota CouchDB (ej. http://couchdb:5984/facturas). Obligatoria en modo servidor.
          </span>
        </div>

        <div class="field-group">
          <label for="input-vlm-url">Endpoint VLM (Opcional)</label>
          <input
            id="input-vlm-url"
            v-model="vlmUrl"
            type="text"
            placeholder="http://servidor:8001/v1"
            :disabled="saving || syncing"
            aria-describedby="vlm-url-help"
            autocomplete="off"
          />
          <span id="vlm-url-help" class="help-text muted">
            Base OpenAI compatible terminada en /v1. Independiente de CouchDB (nunca se deduce de la URL de sync). En blanco usa el sidecar local.
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
      </fieldset>

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
            {{ saving ? 'Guardando y verificando...' : (isServerMode ? 'Guardar y conectar' : 'Confirmar modo local') }}
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
  background: var(--border-soft);
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
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
  background: var(--panel);
  transition: border-color 0.15s, background 0.15s;
}

.mode-label:hover {
  background: #fafaf9;
}

.mode-label.selected {
  border-color: var(--accent);
  background: #fdfdfd;
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

.message-box {
  padding: 10px 14px;
  border-radius: 4px;
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
