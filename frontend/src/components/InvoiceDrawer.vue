<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api, fmtHora, fmtValor, liderIndex, type Candidate, type InvoiceDetail } from '../api'
import ResultBadge from './ResultBadge.vue'

const props = defineProps<{ invoiceId: string | null }>()
const emit = defineEmits<{ close: []; updated: [] }>()

const detail = ref<InvoiceDetail | null>(null)
const error = ref('')
const busy = ref(false)
const motivo = ref('')
const elegidos = ref<Record<string, number>>({}) // field_type -> índice del candidato elegido

watch(
  () => props.invoiceId,
  async (id) => {
    detail.value = null
    error.value = ''
    elegidos.value = {}
    motivo.value = ''
    if (id) await load(id)
  },
  { immediate: true }
)

async function load(id: string) {
  try {
    detail.value = await api.factura(id)
  } catch (e) {
    error.value = String(e)
  }
}

function candidatos(fieldType: string): Candidate[] {
  return detail.value?.fields[fieldType] ?? []
}

function elegido(fieldType: string): number {
  return elegidos.value[fieldType] ?? liderIndex(candidatos(fieldType))
}

const tieneCorreccion = computed(() => {
  if (!detail.value) return false
  return Object.keys(detail.value.fields).some((f) => elegido(f) !== liderIndex(candidatos(f)))
})

/**
 * Resuelve la revisión: confirma los campos cuyo candidato líder se mantiene
 * (`accepted`) y corrige los que el revisor cambia (`corrected`). El backend
 * recalcula la decisión de forma determinista; nunca se fuerza el pago.
 */
async function resolver() {
  if (!detail.value || busy.value) return
  busy.value = true
  error.value = ''
  const d = detail.value
  const accepted: string[] = []
  const corrected: Record<string, unknown> = {}
  for (const fieldType of Object.keys(d.fields)) {
    const cs = candidatos(fieldType)
    if (cs.length === 0) continue
    const i = elegido(fieldType)
    if (i === liderIndex(cs)) accepted.push(fieldType)
    else corrected[fieldType] = cs[i]?.value
  }
  try {
    await api.resolve(d.invoice.id, {
      who: 'revisor',
      reason:
        motivo.value ||
        (Object.keys(corrected).length ? 'corrección en revisión' : 'confirmación en revisión'),
      accepted,
      corrected,
      expected_decision_id: d.decision?.decision_id ?? ''
    })
    motivo.value = ''
    emit('updated')
    await load(d.invoice.id)
  } catch (e) {
    // 409: la decisión cambió desde que se cargó. Se recarga conservando la
    // selección del revisor y se muestra el error para reintentar.
    const msg = String(e)
    await load(d.invoice.id)
    error.value = msg
  } finally {
    busy.value = false
  }
}

function safeParse(s: string): unknown {
  try {
    return JSON.parse(s)
  } catch {
    return s
  }
}
</script>

<template>
  <div v-if="invoiceId" class="backdrop" @click.self="emit('close')">
    <aside class="drawer" role="dialog" aria-modal="true" aria-label="Revisión de factura">
      <div class="head">
        <h2 class="mono">{{ invoiceId }}</h2>
        <button type="button" @click="emit('close')">Cerrar</button>
      </div>

      <p v-if="error" class="error" role="alert">{{ error }}</p>

      <template v-if="detail">
        <section class="panel">
          <div class="head-line">
            <strong class="mono">{{ detail.invoice.file_id }}</strong>
            <ResultBadge :result="detail.decision?.result ?? null" />
            <span v-if="detail.disputed" class="badge disputa">retenida · sin sincronizar</span>
            <span v-else-if="detail.review_state === 'resolved'" class="badge PASS">revisión resuelta</span>
          </div>
          <dl class="meta">
            <dt>UUID interno</dt><dd class="mono">{{ detail.invoice.id }}</dd>
            <dt>sha256</dt><dd class="mono" :title="detail.invoice.sha256">{{ detail.invoice.sha256.slice(0, 16) }}…</dd>
            <dt>Estado</dt><dd>{{ detail.invoice.status }}</dd>
            <dt>Ruta origen</dt><dd class="mono">{{ detail.invoice.source_path || '—' }}</dd>
            <dt>Decisión</dt>
            <dd class="mono">
              {{ detail.decision?.decision_id ?? '—' }}
              <span v-if="detail.decision" class="muted">({{ fmtHora(detail.decision.timestamp) }})</span>
            </dd>
          </dl>
          <p v-if="detail.decision?.result === 'ESCALAR'" class="muted aviso">
            El resultado ESCALAR no autoriza el pago: la revisión solo confirma o corrige la
            lectura y el motor vuelve a decidir.
          </p>
        </section>

        <section class="panel">
          <h3>Reglas</h3>
          <table>
            <thead><tr><th>Código</th><th>Veredicto</th><th>Motivo</th></tr></thead>
            <tbody>
              <tr v-for="r in detail.rule_evaluations" :key="r.code">
                <td class="mono">{{ r.code }}</td>
                <td><span class="badge" :class="r.verdict">{{ r.verdict }}</span></td>
                <td>{{ r.reason }}</td>
              </tr>
              <tr v-if="detail.rule_evaluations.length === 0">
                <td colspan="3" class="muted">sin evaluaciones registradas</td>
              </tr>
            </tbody>
          </table>
        </section>

        <section class="panel">
          <h3>Campos y candidatos</h3>
          <p class="muted">
            Todos los candidatos se conservan. Confirma el candidato correcto por campo; el
            backend registra la procedencia y recalcula la decisión con el mismo motor.
          </p>
          <div v-for="(cs, fieldType) in detail.fields" :key="fieldType" class="campo">
            <div class="campo-head">
              <strong class="mono">{{ fieldType }}</strong>
              <span v-if="elegido(String(fieldType)) !== liderIndex(cs)" class="badge ESCALAR">corregido</span>
            </div>
            <label v-for="(c, i) in cs" :key="c.extractor + i" class="candidato">
              <input
                type="radio"
                :name="`cand-${fieldType}`"
                :checked="elegido(String(fieldType)) === i"
                @change="elegidos[String(fieldType)] = i"
              />
              <span class="mono">{{ fmtValor(c.value) }}</span>
              <span class="muted">· {{ c.extractor }} · {{ Math.round(c.confidence * 100) }}%</span>
            </label>
          </div>
          <p v-if="Object.keys(detail.fields).length === 0" class="muted">sin campos extraídos</p>
          <div class="toolbar aplicar">
            <input v-model="motivo" aria-label="Motivo de la resolución" placeholder="motivo (opcional)" />
            <button type="button" class="primary" :disabled="busy" @click="resolver">
              {{ tieneCorreccion ? 'Aplicar corrección y recalcular' : 'Confirmar lectura y recalcular' }}
            </button>
          </div>
        </section>

        <section v-if="detail.resolution" class="panel">
          <h3>Última resolución</h3>
          <dl class="meta">
            <dt>Quién</dt><dd>{{ detail.resolution.who }}</dd>
            <dt>Cuándo</dt><dd>{{ fmtHora(detail.resolution.timestamp) }}</dd>
            <dt>Motivo</dt><dd>{{ detail.resolution.reason }}</dd>
            <dt>Confirmados</dt><dd class="mono">{{ detail.resolution.accepted.join(', ') || '—' }}</dd>
            <dt>Corregidos</dt>
            <dd class="mono">
              {{ Object.entries(detail.resolution.corrected).map(([k, v]) => `${k}=${v}`).join(', ') || '—' }}
            </dd>
          </dl>
        </section>

        <section class="panel">
          <h3>Overrides previos</h3>
          <table>
            <thead><tr><th>Cuándo</th><th>Campo</th><th>Antes → Después</th><th>Quién</th><th>Motivo</th></tr></thead>
            <tbody>
              <tr v-for="o in detail.overrides" :key="o.id">
                <td class="muted">{{ fmtHora(o.timestamp) }}</td>
                <td class="mono">{{ o.field_type }}</td>
                <td class="mono">{{ fmtValor(safeParse(o.before)) }} → {{ fmtValor(safeParse(o.after)) }}</td>
                <td>{{ o.who }}/{{ o.rung }}</td>
                <td>{{ o.reason }}</td>
              </tr>
              <tr v-if="detail.overrides.length === 0">
                <td colspan="5" class="muted">sin overrides</td>
              </tr>
            </tbody>
          </table>
        </section>
      </template>
    </aside>
  </div>
</template>

<style scoped>
.backdrop {
  position: fixed;
  inset: 0;
  background: rgba(42, 23, 15, 0.35);
  display: flex;
  justify-content: flex-end;
  z-index: 10;
}
.drawer {
  width: min(600px, 100%);
  height: 100%;
  overflow-y: auto;
  background: var(--bg);
  border-left: 3px solid var(--ink);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.head { display: flex; justify-content: space-between; align-items: center; gap: 10px; }
.drawer .panel { overflow-x: auto; }
.head-line { display: flex; gap: 10px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }
.meta {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 2px 12px;
  margin: 0;
}
.meta dt { color: var(--muted); }
.meta dd { margin: 0; overflow-wrap: anywhere; }
.aviso { margin: 10px 0 0; }
.campo { margin-bottom: 10px; }
.campo-head { display: flex; gap: 8px; align-items: center; margin-bottom: 2px; }
.candidato { display: flex; gap: 8px; align-items: baseline; padding: 2px 0 2px 12px; }
.aplicar { margin-top: 10px; }
</style>
