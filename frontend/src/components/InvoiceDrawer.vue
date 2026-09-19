<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api, fmtHora, fmtValor, type Candidate, type InvoiceDetail } from '../api'
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
    if (id) await load(id)
  },
  { immediate: true }
)

async function load(id: string) {
  error.value = ''
  try {
    detail.value = await api.factura(id)
  } catch (e) {
    error.value = String(e)
  }
}

function candidatos(fieldType: string): Candidate[] {
  return detail.value?.fields[fieldType] ?? []
}

function lider(fieldType: string): number {
  // candidato líder: mayor confianza (el motor colapsa solo al evaluar)
  const cs = candidatos(fieldType)
  let best = 0
  cs.forEach((c, i) => {
    if (c.confidence > cs[best].confidence) best = i
  })
  return best
}

function elegido(fieldType: string): number {
  return elegidos.value[fieldType] ?? lider(fieldType)
}

async function aplicar() {
  if (!detail.value || busy.value) return
  busy.value = true
  error.value = ''
  try {
    for (const fieldType of Object.keys(detail.value.fields)) {
      const cs = candidatos(fieldType)
      const i = elegido(fieldType)
      const after = cs[i]?.value
      const before = cs[lider(fieldType)]?.value
      await api.override(detail.value.invoice.id, {
        field_type: fieldType,
        before,
        after,
        who: 'revisor',
        rung: 'review-ui',
        reason: motivo.value || (before === after ? 'confirmación en revisión' : 'corrección en revisión')
      })
    }
    await api.reprocesar(detail.value.invoice.file_id, detail.value.invoice.id)
    motivo.value = ''
    emit('updated')
    await load(detail.value.invoice.id)
  } catch (e) {
    error.value = String(e)
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

const tieneCorreccion = computed(() => {
  if (!detail.value) return false
  return Object.keys(detail.value.fields).some((f) => elegido(f) !== lider(f))
})
</script>

<template>
  <div v-if="invoiceId" class="backdrop" @click.self="emit('close')">
    <aside class="drawer">
      <div class="head">
        <h2 class="mono">{{ invoiceId }}</h2>
        <button @click="emit('close')">Cerrar</button>
      </div>

      <p v-if="error" class="error">{{ error }}</p>

      <template v-if="detail">
        <section class="panel">
          <div class="head-line">
            <strong class="mono">{{ detail.invoice.file_id }}</strong>
            <ResultBadge :result="detail.decision?.result ?? null" />
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
            Todos los candidatos se conservan. Elige el correcto por campo; el override
            afecta solo a la extracción y la decisión se recalcula con el mismo motor.
          </p>
          <div v-for="(cs, fieldType) in detail.fields" :key="fieldType" class="campo">
            <div class="campo-head">
              <strong class="mono">{{ fieldType }}</strong>
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
            <input v-model="motivo" placeholder="motivo (opcional)" />
            <button class="primary" :disabled="busy" @click="aplicar">
              {{ tieneCorreccion ? 'Aplicar corrección y reprocesar' : 'Confirmar lectura y reprocesar' }}
            </button>
          </div>
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
  background: rgba(0, 0, 0, 0.2);
  display: flex;
  justify-content: flex-end;
  z-index: 10;
}
.drawer {
  width: min(560px, 100%);
  height: 100%;
  overflow-y: auto;
  background: var(--bg);
  border-left: 1px solid var(--border);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.head { display: flex; justify-content: space-between; align-items: center; }
.head-line { display: flex; gap: 10px; align-items: center; margin-bottom: 8px; }
.meta {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 2px 12px;
  margin: 0;
}
.meta dt { color: var(--muted); }
.meta dd { margin: 0; overflow-wrap: anywhere; }
.campo { margin-bottom: 10px; }
.campo-head { margin-bottom: 2px; }
.candidato { display: flex; gap: 8px; align-items: baseline; padding: 2px 0 2px 12px; }
.aplicar { margin-top: 10px; }
.raw pre {
  background: var(--panel);
  border: 1px solid var(--border-soft);
  border-radius: 4px;
  padding: 10px;
  overflow-x: auto;
}
</style>
