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
const cargando = ref(false) // hay una carga en vuelo (primera o de refresco)
const cargado = ref(false) // la primera carga ya resolvió: hay algo que mostrar

let timer: ReturnType<typeof setInterval> | undefined

async function load() {
  cargando.value = true
  try {
    facturas.value = await api.facturas()
    error.value = ''
    actualizado.value = new Date()
  } catch (e) {
    error.value = String(e)
  } finally {
    cargando.value = false
    cargado.value = true
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
      <template v-if="cargado">
        <p class="big">{{ abiertas.length }}</p>
        <!-- el total agrupa dos estados distintos: sin decisión y escaladas -->
        <p class="muted desglose">
          {{ porResultado.pendiente }} en revisión (sin decisión) ·
          {{ porResultado.ESCALAR }} escaladas
        </p>
      </template>
      <p v-else class="cargando" aria-live="polite">
        <span class="spinner mini"></span> Cargando…
      </p>
      <ul>
        <li v-for="[ext, n] in porTipo" :key="ext">{{ n }} {{ ext }}</li>
        <li v-if="porTipo.length === 0" class="muted">—</li>
      </ul>
      <p class="muted tick">
        actualizado {{ actualizado?.toLocaleTimeString('es-ES') ?? '—' }}
        <span v-if="cargando && cargado" class="refresco">
          <span class="spinner mini"></span> actualizando…
        </span>
      </p>
    </section>

    <!-- resumen por resultado (derivado de las facturas cargadas) -->
    <section class="panel resumen">
      <h3>Resumen</h3>
      <div class="resumen-grid" :class="{ 'sin-datos': !cargado }" :aria-busy="!cargado">
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
    <!-- primera carga: esqueleto con la geometría de la tabla; el refresco de
         10 s nunca la vacía (solo el aviso sutil de `.refresco`) -->
    <div v-if="!cargado" class="esqueleto-tabla" aria-live="polite">
      <p class="cargando"><span class="spinner"></span> Cargando facturas…</p>
      <div v-for="n in 4" :key="`fila-${n}`" class="esqueleto-fila" aria-hidden="true">
        <span class="esqueleto esq-nombre"></span>
        <span class="esqueleto esq-ext"></span>
        <span class="esqueleto esq-num"></span>
        <span class="esqueleto esq-num"></span>
        <span class="esqueleto esq-num"></span>
      </div>
    </div>
    <InvoiceTable
      v-else
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
.desglose { margin: 0 0 6px; font-size: 12px; }
.tick { margin: 8px 0 0; font-size: 12px; }
.tick .refresco { margin-left: 8px; }
.resumen-grid { display: flex; flex-wrap: wrap; gap: 14px 22px; }
.sin-datos { opacity: 0.45; }
.resumen-grid div { display: flex; align-items: center; gap: 8px; }
.resumen-grid strong { font-family: var(--display); font-size: 20px; font-weight: 400; }
.table-panel { padding: 4px 8px; }
.toolbar { margin-bottom: 10px; }

/* Esqueleto de la primera carga: misma rejilla que la tabla, sin salto visual. */
.esqueleto-tabla .cargando { padding: 12px; margin: 0; }
.esqueleto-fila {
  display: grid;
  grid-template-columns: 2fr 0.8fr 0.8fr 0.8fr 1.2fr;
  gap: 10px;
  padding: 8px 12px;
}
.esq-nombre { width: 80%; }
.esq-ext { width: 52px; }
.esq-num { width: 48px; }

@media (max-width: 720px) {
  .cards { grid-template-columns: 1fr; }
}
</style>
