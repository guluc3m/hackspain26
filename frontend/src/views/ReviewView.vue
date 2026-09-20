<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { api, confirmarLectura, fmtHora, type ReviewItem } from '../api'
import InvoiceDrawer from '../components/InvoiceDrawer.vue'

const items = ref<ReviewItem[]>([])
const error = ref('')
const cargando = ref(false) // petición en vuelo (primera carga o refresco de 10 s)
const cargado = ref(false) // la primera carga ya resolvió: la tabla tiene datos reales
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
    cargado.value = true
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
    <span v-if="cargado" class="muted">{{ items.length }} pendiente(s)</span>
    <span v-else class="cargando" aria-live="polite">
      <span class="spinner mini"></span> Cargando revisiones…
    </span>
    <span v-if="cargando && cargado" class="refresco" aria-live="polite">
      <span class="spinner mini"></span> actualizando…
    </span>
  </div>

  <p v-if="error" class="error" role="alert">{{ error }}</p>

  <div
    class="panel table-panel"
    :class="{ recargando: cargando && cargado }"
    :aria-busy="cargando"
  >
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
        <tr v-if="cargado && items.length === 0">
          <td colspan="6" class="muted">sin disputas pendientes</td>
        </tr>
        <!-- primera carga: filas de esqueleto con la geometría real de la tabla;
             el panel nunca se queda vacío ni anuncia «sin disputas» sin saberlo -->
        <template v-if="!cargado">
          <tr v-for="n in 3" :key="`esqueleto-${n}`" class="esqueleto-fila" aria-hidden="true">
            <td><span class="esqueleto esq-fichero"></span></td>
            <td><span class="esqueleto esq-badge"></span></td>
            <td><span class="esqueleto esq-badge"></span></td>
            <td><span class="esqueleto esq-motivo"></span></td>
            <td><span class="esqueleto esq-desde"></span></td>
            <td><span class="esqueleto esq-acciones"></span></td>
          </tr>
        </template>
      </tbody>
    </table>
  </div>

  <InvoiceDrawer :invoice-id="drawerId" @close="drawerId = null" @updated="load" />
</template>

<style scoped>
.intro { margin: 0 0 12px; max-width: 760px; }
.toolbar { margin-bottom: 10px; }
.toolbar .cargando { padding: 0; }
.table-panel { padding: 4px 8px; }

/* Refresco (10 s o tras confirmar): la tabla sigue visible, solo se atenúa el
   cuerpo; la cabecera y el alto del panel se conservan. */
.table-panel.recargando tbody { opacity: 0.5; }

/* Primera carga: barras de esqueleto con el ancho de cada columna. */
.esqueleto-fila .esqueleto { vertical-align: middle; }
.esq-fichero { width: 70%; }
.esq-badge { width: 62px; }
.esq-motivo { width: 55%; }
.esq-desde { width: 84px; }
.esq-acciones { width: 150px; }
</style>
