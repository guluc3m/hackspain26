<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { api, confirmarLectura, fmtHora, type ReviewItem } from '../api'
import InvoiceDrawer from '../components/InvoiceDrawer.vue'

const items = ref<ReviewItem[]>([])
const error = ref('')
const cargando = ref(false)
const drawerId = ref<string | null>(null)
const busyKey = ref<string | null>(null)

let timer: ReturnType<typeof setInterval> | undefined

async function load() {
  cargando.value = true
  try {
    items.value = (await api.revision()).items
    error.value = ''
  } catch (e) {
    error.value = String(e)
  } finally {
    cargando.value = false
  }
}

onMounted(() => {
  load()
  timer = setInterval(load, 10_000) // la cola respira sola, como el Dashboard
})
onUnmounted(() => clearInterval(timer))

/** Confirmación directa de la lectura: acepta los candidatos líderes y resuelve. */
async function confirmar(it: ReviewItem) {
  busyKey.value = it.file_key
  try {
    await confirmarLectura(it.file_key)
    await load()
  } catch (e) {
    error.value = String(e)
  } finally {
    busyKey.value = null
  }
}
</script>

<template>
  <h2>Revisión</h2>
  <p class="muted intro">
    Facturas escaladas pendientes de revisión humana. Mientras no se resuelven, su
    decisión queda retenida y no se sincroniza. Resolver confirma o corrige la
    lectura; el motor recalcula la decisión (nunca se fuerza el pago).
  </p>

  <div class="toolbar">
    <span class="muted">{{ items.length }} pendiente(s)</span>
  </div>

  <p v-if="error" class="error" role="alert">{{ error }}</p>

  <div class="panel table-panel">
    <table>
      <thead>
        <tr>
          <th>Fichero</th>
          <th>Resultado</th>
          <th>Estado</th>
          <th>Motivo</th>
          <th>Desde</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="it in items" :key="it.file_key">
          <td><button type="button" class="link mono" @click="drawerId = it.file_key">{{ it.file_id }}</button></td>
          <td><span class="badge" :class="it.result">{{ it.result }}</span></td>
          <td><span class="badge disputa">retenida</span></td>
          <td>{{ it.reason }}</td>
          <td class="muted">{{ fmtHora(it.since) }}</td>
          <td>
            <button
              type="button"
              class="primary"
              :disabled="busyKey === it.file_key"
              title="Aceptar los candidatos líderes: resuelve la revisión (el motor recalcula)"
              @click="confirmar(it)"
            >
              Confirmar lectura
            </button>
            <button type="button" @click="drawerId = it.file_key">Revisar</button>
          </td>
        </tr>
        <tr v-if="items.length === 0">
          <td colspan="6" class="muted">sin disputas pendientes</td>
        </tr>
      </tbody>
    </table>
  </div>

  <InvoiceDrawer :invoice-id="drawerId" @close="drawerId = null" @updated="load" />
</template>

<style scoped>
.intro { margin: 0 0 12px; max-width: 760px; }
.toolbar { margin-bottom: 10px; }
.table-panel { padding: 4px 8px; }
</style>
