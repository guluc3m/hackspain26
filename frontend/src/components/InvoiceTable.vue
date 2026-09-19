<script setup lang="ts">
import { computed } from 'vue'
import { fileExt, type FacturaRow } from '../api'
import ResultBadge from './ResultBadge.vue'

const props = defineProps<{
  rows: FacturaRow[]
  showGate?: boolean
  showFolder?: boolean
  busyId?: string | null
}>()

const emit = defineEmits<{
  open: [row: FacturaRow]
  accept: [row: FacturaRow]
  decline: [row: FacturaRow]
  process: [row: FacturaRow]
  logs: [row: FacturaRow]
}>()

const totalColumnas = computed(
  () => 4 + (props.showFolder ? 1 : 0) + (props.showGate ? 1 : 0) + 1 // + logs
)
</script>

<template>
  <table>
    <thead>
      <tr>
        <th>Nombre</th>
        <th>Archivo</th>
        <th title="Pasadas del pipeline registradas en el ledger (append-only)">Iteraciones</th>
        <th title="Peor campo: mejor candidato de lectura por campo, mínimo entre campos">Confianza</th>
        <th v-if="showFolder">Carpeta</th>
        <th v-if="showGate">Decisión</th>
        <th>Logs</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="row in rows" :key="row.id">
        <td><button class="link mono" @click="emit('open', row)">{{ row.file_id }}</button></td>
        <td><span class="badge tipo">{{ fileExt(row.file_id) }}</span></td>
        <td>{{ row.iterations }}</td>
        <td :class="{ warn: row.confidence !== null && row.confidence < 0.6 }">
          {{ row.confidence === null ? '—' : Math.round(row.confidence * 100) + '%' }}
        </td>
        <td v-if="showFolder" class="mono" :title="row.source_path ?? ''">
          {{ row.folder ?? '—' }}
        </td>
        <td v-if="showGate">
          <template v-if="row.result === 'ESCALAR'">
            <button
              class="primary"
              :disabled="busyId === row.id"
              title="Aceptar la lectura actual: override de confirmación y reprocesado (el motor decide)"
              @click="emit('accept', row)"
            >
              Aceptar
            </button>
            <button
              class="danger"
              :disabled="busyId === row.id"
              title="Corregir la lectura: elegir candidato, override y reprocesado (el motor decide)"
              @click="emit('decline', row)"
            >
              Corregir
            </button>
          </template>
          <button
            v-else-if="row.result === null"
            class="secondary"
            :disabled="busyId === row.id"
            title="Procesar ahora el PDF pendiente"
            @click="emit('process', row)"
          >
            Procesar
          </button>
          <template v-else><ResultBadge :result="row.result" /></template>
        </td>
        <td>
          <button
            class="link"
            title="Ver todos los logs de esta factura en el buscador"
            @click="emit('logs', row)"
          >
            logs
          </button>
        </td>
      </tr>
      <tr v-if="rows.length === 0">
        <td :colspan="totalColumnas" class="muted">sin facturas</td>
      </tr>
    </tbody>
  </table>
</template>

<style scoped>
td .primary, td .danger, td .secondary { margin-right: 6px; }
.warn { color: var(--warn-fg); }
</style>
