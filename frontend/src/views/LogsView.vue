<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, fmtHora, fmtValor, type LogEvent, type LogsResponse } from '../api'
import InvoiceDrawer from '../components/InvoiceDrawer.vue'

const q = ref('')
const eventType = ref('')
const limit = ref(200)
const data = ref<LogsResponse | null>(null)
const error = ref('')
const drawerId = ref<string | null>(null)
const cargando = ref(false)

async function load() {
  cargando.value = true
  try {
    data.value = await api.logs({ q: q.value, event_type: eventType.value, limit: limit.value })
    error.value = ''
  } catch (e) {
    error.value = String(e)
  } finally {
    cargando.value = false
  }
}
onMounted(load)

function resumen(e: LogEvent): string {
  switch (e.type) {
    case 'invoice_seen':
      return `${String(e.file_id)} visto · sha ${String(e.sha256 ?? '').slice(0, 12)}…`
    case 'decision':
      return `${String(e.file_id)} → ${String(e.result)} (run ${String(e.run_id)})`
    case 'override':
      return `${String(e.field_type)}: ${fmtValor(e.before)} → ${fmtValor(e.after)} · ${String(e.who)}/${String(e.rung)}${e.reason ? ` · ${String(e.reason)}` : ''}`
    case 'item_error':
      return `${String(e.file_id)}: ${String(e.error)}`
    default:
      return JSON.stringify({ ...e, seq: undefined, ts: undefined, type: undefined })
  }
}

function bruto(e: LogEvent): string {
  return JSON.stringify(e, null, 2)
}
</script>

<template>
  <h2>Logs</h2>
  <p class="muted">
    Ledger append-only (data/ledger.jsonl): cada transición de estado, en orden.
    Busca por texto libre o filtra por tipo; «ver» abre la traza completa de la factura.
  </p>

  <div class="toolbar">
    <input
      v-model="q"
      placeholder="buscar (texto libre sobre el evento)…"
      @keyup.enter="load"
    />
    <select v-model="eventType">
      <option value="">todos los tipos</option>
      <option v-for="t in data?.types ?? []" :key="t" :value="t">{{ t }}</option>
    </select>
    <select v-model.number="limit">
      <option :value="100">100</option>
      <option :value="200">200</option>
      <option :value="500">500</option>
    </select>
    <button class="primary" :disabled="cargando" @click="load">Buscar</button>
  </div>

  <p v-if="error" class="error">{{ error }}</p>

  <p v-if="data" class="muted contador">
    {{ data.total }} eventos coinciden · mostrando los {{ data.items.length }} más recientes
  </p>

  <div class="panel lista">
    <div v-for="e in data?.items ?? []" :key="e.seq" class="evento">
      <span class="mono seq">#{{ e.seq }}</span>
      <span class="mono hora">{{ fmtHora(e.ts) }}</span>
      <span class="badge tipo">{{ e.type }}</span>
      <span class="resumen mono">{{ resumen(e) }}</span>
      <button v-if="e.invoice_id" class="link" @click="drawerId = String(e.invoice_id)">ver</button>
      <details>
        <summary class="muted">json</summary>
        <pre>{{ bruto(e) }}</pre>
      </details>
    </div>
    <p v-if="data && data.items.length === 0" class="muted">sin eventos</p>
  </div>

  <InvoiceDrawer :invoice-id="drawerId" @close="drawerId = null" @updated="load" />
</template>

<style scoped>
.toolbar { margin-bottom: 10px; }
.toolbar input { min-width: 280px; }
.contador { margin: 0 0 8px; }
.lista { padding: 4px 12px; }
.evento {
  display: flex;
  gap: 10px;
  align-items: baseline;
  padding: 6px 0;
  border-bottom: 1px solid var(--border-soft);
  flex-wrap: wrap;
}
.evento:last-child { border-bottom: none; }
.seq { color: var(--muted); flex: none; width: 52px; }
.hora { color: var(--muted); flex: none; }
.resumen { overflow-wrap: anywhere; }
.evento details { flex-basis: 100%; }
.evento details pre {
  background: var(--panel);
  border: 1px solid var(--border-soft);
  border-radius: 4px;
  padding: 8px;
  overflow-x: auto;
}
.evento details summary { cursor: pointer; }
</style>
