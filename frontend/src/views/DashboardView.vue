<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api, confirmarLectura, fileExt, type FacturaRow } from '../api'
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
    await api.reprocesar(row.file_id)
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

    <!-- bloque reservado para otra información -->
    <section class="panel reserved">
      <span class="muted">Reservado</span>
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
.big { font-size: 40px; font-weight: 700; margin: 4px 0; }
.pending ul { margin: 0; padding-left: 18px; }
.tick { margin: 8px 0 0; font-size: 12px; }
.reserved {
  display: flex;
  align-items: center;
  justify-content: center;
  border-style: dashed;
  min-height: 140px;
}
.table-panel { padding: 4px 8px; }
.toolbar { margin-bottom: 10px; }
</style>
