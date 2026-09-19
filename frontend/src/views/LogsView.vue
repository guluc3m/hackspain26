<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { api, fmtHora, type LogItem, type LogsResponse } from '../api'
import { logsInvoice } from '../nav'
import InvoiceDrawer from '../components/InvoiceDrawer.vue'

const q = ref('')
const eventType = ref('')
const invoiceFiltro = ref('')
const limit = ref(200)
const offset = ref(0)
const data = ref<LogsResponse | null>(null)
const error = ref('')
const drawerId = ref<string | null>(null)
const cargando = ref(false)
const abiertos = ref<Set<string>>(new Set())

function clave(e: LogItem): string {
  return String(e.seq)
}

async function load(reset = false) {
  if (reset) offset.value = 0
  cargando.value = true
  try {
    data.value = await api.logs({
      q: q.value,
      event_type: eventType.value,
      invoice: invoiceFiltro.value,
      limit: limit.value,
      offset: offset.value
    })
    error.value = ''
    abiertos.value = new Set()
  } catch (e) {
    error.value = String(e)
  } finally {
    cargando.value = false
  }
}

// llega de un botón «logs» de una factura: mismo sistema de filtro
onMounted(() => {
  invoiceFiltro.value = logsInvoice.value
  load()
})
watch(logsInvoice, (v) => {
  invoiceFiltro.value = v
  load(true)
})

function quitarFiltro() {
  invoiceFiltro.value = ''
  load(true)
}

function alternar(e: LogItem) {
  const k = clave(e)
  const next = new Set(abiertos.value)
  if (next.has(k)) next.delete(k)
  else next.add(k)
  abiertos.value = next
}

/** JSON crudo de la entrada, solo cuando el usuario lo despliega. */
function bruto(e: LogItem): string {
  return JSON.stringify(e.payload ?? e, null, 2)
}

const total = () => data.value?.total ?? 0
const desde = () => (total() === 0 ? 0 : offset.value + 1)
const hasta = () => Math.min(offset.value + (data.value?.items.length ?? 0), total())
</script>

<template>
  <h2>Logs</h2>
  <p class="muted intro">
    Cada entrada es una referencia mínima (tipo + IDs). El resumen lo resuelve el
    backend contra la base de datos; el JSON crudo se muestra solo al desplegarlo.
  </p>

  <form class="toolbar" role="search" @submit.prevent="load(true)">
    <input
      v-model="invoiceFiltro"
      class="por-factura"
      aria-label="Filtrar por nombre de factura"
      placeholder="factura (nombre de fichero)…"
      title="Solo las entradas de esta factura"
    />
    <input
      v-model="q"
      aria-label="Buscar texto libre en las entradas"
      placeholder="buscar…"
    />
    <select v-model="eventType" aria-label="Filtrar por tipo de evento">
      <option value="">todos los tipos</option>
      <option v-for="t in data?.types ?? []" :key="t" :value="t">{{ t }}</option>
    </select>
    <select v-model.number="limit" aria-label="Entradas por página">
      <option :value="100">100 / pág.</option>
      <option :value="200">200 / pág.</option>
      <option :value="500">500 / pág.</option>
    </select>
    <button type="submit" class="primary" :disabled="cargando">Buscar</button>
    <button v-if="invoiceFiltro" type="button" class="link" @click="quitarFiltro">
      quitar filtro de factura
    </button>
  </form>

  <p v-if="error" class="error" role="alert">{{ error }}</p>

  <div v-if="data" class="pager">
    <span class="muted">
      {{ total() }} entradas · mostrando {{ desde() }}–{{ hasta() }}
    </span>
    <span class="pager-btns">
      <button
        type="button"
        :disabled="offset === 0 || cargando"
        @click="offset = Math.max(0, offset - limit); load()"
      >
        ← Anterior
      </button>
      <button
        type="button"
        :disabled="offset + limit >= total() || cargando"
        @click="offset += limit; load()"
      >
        Siguiente →
      </button>
    </span>
  </div>

  <ul class="panel lista">
    <li v-for="e in data?.items ?? []" :key="clave(e)" class="log-item">
      <div class="log-main">
        <time class="log-ts mono">{{ fmtHora(e.ts) }}</time>
        <span class="badge tipo">{{ e.type }}</span>
        <span class="log-file mono" :title="e.file_id ?? ''">{{ e.file_id ?? '—' }}</span>
        <span class="log-summary">{{ e.summary }}</span>
        <span class="log-actions">
          <button v-if="e.invoice_id" type="button" class="link" @click="drawerId = e.invoice_id">
            ver
          </button>
          <button
            type="button"
            class="link"
            :aria-expanded="abiertos.has(clave(e))"
            @click="alternar(e)"
          >
            {{ abiertos.has(clave(e)) ? 'ocultar' : 'detalles' }}
          </button>
        </span>
      </div>
      <pre v-if="abiertos.has(clave(e))" class="raw">{{ bruto(e) }}</pre>
    </li>
    <li v-if="data && data.items.length === 0" class="muted empty">sin entradas</li>
  </ul>

  <InvoiceDrawer :invoice-id="drawerId" @close="drawerId = null" @updated="load()" />
</template>

<style scoped>
.intro { margin: 0 0 12px; max-width: 760px; }
.toolbar { margin-bottom: 12px; }
.toolbar input { min-width: 200px; }
.toolbar .por-factura { min-width: 240px; }

.pager {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.pager-btns { display: flex; gap: 6px; }

.lista {
  list-style: none;
  margin: 0;
  padding: 0;
}
.log-item { border-bottom: 1px solid var(--border-soft); }
.log-item:last-child { border-bottom: none; }

.log-main {
  display: grid;
  grid-template-columns: 132px 108px minmax(120px, 200px) 1fr auto;
  gap: 10px;
  align-items: baseline;
  padding: 7px 12px;
}
.log-ts { color: var(--muted); white-space: nowrap; }
.log-file {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.log-summary { overflow-wrap: anywhere; }
.log-actions {
  display: flex;
  gap: 10px;
  white-space: nowrap;
}
.log-item .raw { margin: 0 12px 10px; }
.empty { padding: 12px; }

@media (max-width: 720px) {
  .log-main {
    grid-template-columns: 1fr auto;
    grid-template-areas:
      'ts actions'
      'type type'
      'file file'
      'summary summary';
    row-gap: 4px;
  }
  .log-ts { grid-area: ts; }
  .log-actions { grid-area: actions; }
  .log-main .badge.tipo { grid-area: type; justify-self: start; }
  .log-file { grid-area: file; white-space: normal; }
  .log-summary { grid-area: summary; }
}
</style>
