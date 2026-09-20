<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api, confirmarLectura, fileExt, type FacturaRow } from '../api'
import { irALogsDe } from '../nav'
import InvoiceDrawer from '../components/InvoiceDrawer.vue'
import InvoiceTable from '../components/InvoiceTable.vue'

const facturas = ref<FacturaRow[]>([])
const error = ref('')
const filtro = ref<'abiertas' | 'resueltas'>('abiertas')
const drawerId = ref<string | null>(null)
const busyId = ref<string | null>(null)
const actualizado = ref<Date | null>(null)

let timer: ReturnType<typeof setInterval> | undefined

async function load() {
  try {
    facturas.value = await api.facturas()
    error.value = ''
    actualizado.value = new Date()
  } catch (e) {
    error.value = String(e)
  }
}

onMounted(() => {
  load()
  timer = setInterval(load, 10_000) // "ticking": el contador respira solo
})
onUnmounted(() => clearInterval(timer))

// abiertas = pendientes de decisión del motor o escaladas (revisión humana)
const abiertas = computed(() =>
  facturas.value.filter((f) => f.result === null || f.result === 'ESCALAR')
)
const resueltas = computed(() =>
  facturas.value.filter((f) => f.result === 'PAGAR' || f.result === 'NO_PAGAR')
)

const visibles = computed(() => (filtro.value === 'abiertas' ? abiertas.value : resueltas.value))

// desglose por extensión del nombre de fichero (p. ej. "502 PDFs")
const porTipo = computed(() => {
  const counts = new Map<string, number>()
  for (const f of abiertas.value) {
    const ext = fileExt(f.file_id)
    counts.set(ext, (counts.get(ext) ?? 0) + 1)
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1])
})

// recuento global por resultado (derivado de las facturas ya cargadas)
const porResultado = computed(() => {
  const counts = { PAGAR: 0, NO_PAGAR: 0, ESCALAR: 0, pendiente: 0 }
  for (const f of facturas.value) {
    if (f.result === 'PAGAR') counts.PAGAR++
    else if (f.result === 'NO_PAGAR') counts.NO_PAGAR++
    else if (f.result === 'ESCALAR') counts.ESCALAR++
    else counts.pendiente++
  }
  return counts
})

// disputadas: escaladas pendientes de revisión, retenidas sin sincronizar
const disputadas = computed(() => facturas.value.filter((f) => f.disputed))

async function aceptar(row: FacturaRow) {
  busyId.value = row.id
  try {
    await confirmarLectura(row.id)
    await load()
  } catch (e) {
    error.value = String(e)
  } finally {
    busyId.value = null
  }
}

async function procesar(row: FacturaRow) {
  busyId.value = row.id
  try {
    await api.reprocesar(row.file_id, row.id)
    await load()
  } catch (e) {
    error.value = String(e)
  } finally {
    busyId.value = null
  }
}
</script>

<template>
  <h2>Dashboard</h2>

  <div class="cards">
    <section class="panel pending">
      <h3>Facturas pendientes</h3>
      <p class="big">{{ abiertas.length }}</p>
      <ul>
        <li v-for="[ext, n] in porTipo" :key="ext">{{ n }} {{ ext }}</li>
        <li v-if="porTipo.length === 0" class="muted">—</li>
      </ul>
      <p class="muted tick">
        actualizado {{ actualizado?.toLocaleTimeString('es-ES') ?? '—' }}
      </p>
    </section>

    <!-- resumen por resultado (derivado de las facturas cargadas) -->
    <section class="panel resumen">
      <h3>Resumen</h3>
      <div class="resumen-grid">
        <div><span class="badge PAGAR">PAGAR</span><strong>{{ porResultado.PAGAR }}</strong></div>
        <div><span class="badge NO_PAGAR">NO_PAGAR</span><strong>{{ porResultado.NO_PAGAR }}</strong></div>
        <div><span class="badge ESCALAR">ESCALAR</span><strong>{{ porResultado.ESCALAR }}</strong></div>
        <div><span class="badge pendiente">pendiente</span><strong>{{ porResultado.pendiente }}</strong></div>
        <div><span class="badge disputa">retenidas</span><strong>{{ disputadas.length }}</strong></div>
      </div>
    </section>
  </div>

  <div class="toolbar">
    <div class="chips">
      <button class="chip" :class="{ active: filtro === 'abiertas' }" @click="filtro = 'abiertas'">
        Abiertas ({{ abiertas.length }})
      </button>
      <button class="chip" :class="{ active: filtro === 'resueltas' }" @click="filtro = 'resueltas'">
        Resueltas ({{ resueltas.length }})
      </button>
    </div>
  </div>

  <p v-if="error" class="error">{{ error }}</p>

  <div class="panel table-panel">
    <InvoiceTable
      :rows="visibles"
      show-gate
      :busy-id="busyId"
      @open="drawerId = $event.id"
      @accept="aceptar"
      @decline="drawerId = $event.id"
      @process="procesar"
      @logs="irALogsDe($event.file_id)"
    />
  </div>

  <InvoiceDrawer :invoice-id="drawerId" @close="drawerId = null" @updated="load" />
</template>

<style scoped>
.cards {
  display: grid;
  grid-template-columns: minmax(260px, 1fr) 2fr;
  gap: 12px;
  margin-bottom: 14px;
}
.big {
  font-family: var(--display);
  font-size: 40px;
  font-weight: 400;
  margin: 4px 0;
  color: var(--ink);
}
.pending ul { margin: 0; padding-left: 18px; }
.tick { margin: 8px 0 0; font-size: 12px; }
.resumen-grid { display: flex; flex-wrap: wrap; gap: 14px 22px; }
.resumen-grid div { display: flex; align-items: center; gap: 8px; }
.resumen-grid strong { font-family: var(--display); font-size: 20px; font-weight: 400; }
.table-panel { padding: 4px 8px; }
.toolbar { margin-bottom: 10px; }

@media (max-width: 720px) {
  .cards { grid-template-columns: 1fr; }
}
</style>
