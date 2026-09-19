<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api, type FacturaRow, type Resultado } from '../api'
import { irALogsDe } from '../nav'
import InvoiceDrawer from '../components/InvoiceDrawer.vue'
import InvoiceTable from '../components/InvoiceTable.vue'

const facturas = ref<FacturaRow[]>([])
const error = ref('')
const filtro = ref<'todos' | Resultado | 'pendiente' | 'disputadas'>('todos')
const busqueda = ref('')
const drawerId = ref<string | null>(null)

async function load() {
  try {
    facturas.value = await api.facturas()
    error.value = ''
  } catch (e) {
    error.value = String(e)
  }
}
onMounted(load)

const opciones: { id: typeof filtro.value; label: string }[] = [
  { id: 'todos', label: 'Todos' },
  { id: 'PAGAR', label: 'PAGAR' },
  { id: 'NO_PAGAR', label: 'NO_PAGAR' },
  { id: 'ESCALAR', label: 'ESCALAR' },
  { id: 'disputadas', label: 'Disputadas' },
  { id: 'pendiente', label: 'pendiente' }
]

const visibles = computed(() =>
  facturas.value.filter((f) => {
    if (filtro.value === 'disputadas') {
      if (!f.disputed) return false
    } else if (filtro.value === 'pendiente') {
      if (f.result !== null) return false
    } else if (filtro.value !== 'todos' && f.result !== filtro.value) {
      return false
    }
    if (busqueda.value && !f.file_id.toLowerCase().includes(busqueda.value.toLowerCase())) {
      return false
    }
    return true
  })
)
</script>

<template>
  <h2>Invoices</h2>

  <div class="toolbar">
    <div class="chips">
      <button
        v-for="o in opciones"
        :key="o.id"
        class="chip"
        :class="{ active: filtro === o.id }"
        @click="filtro = o.id"
      >
        {{ o.label }}
      </button>
    </div>
    <input v-model="busqueda" placeholder="buscar por nombre…" />
    <button @click="load">Actualizar</button>
  </div>

  <p v-if="error" class="error">{{ error }}</p>

  <div class="panel table-panel">
    <InvoiceTable
      :rows="visibles"
      show-folder
      @open="drawerId = $event.id"
      @logs="irALogsDe($event.file_id)"
    />
  </div>

  <InvoiceDrawer :invoice-id="drawerId" @close="drawerId = null" @updated="load" />
</template>

<style scoped>
.toolbar { margin-bottom: 10px; }
.table-panel { padding: 4px 8px; }
</style>
