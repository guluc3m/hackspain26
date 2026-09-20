<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { api, fmtHora, fmtValor, liderIndex, type Candidate, type InvoiceDetail } from '../api'
import ResultBadge from './ResultBadge.vue'

const props = defineProps<{ invoiceId: string | null }>()
const emit = defineEmits<{ close: []; updated: [] }>()

const detail = ref<InvoiceDetail | null>(null)
const error = ref('')
const busy = ref(false)
const cargando = ref(false) // detalle en vuelo: el drawer nunca se queda en blanco
const motivo = ref('')
/** Selección del revisor por campo: candidato, descarte explícito o texto libre. */
type Seleccion = { tipo: 'candidato'; indice: number } | { tipo: 'descartar' } | { tipo: 'texto' }

const elegidos = ref<Record<string, Seleccion>>({}) // field_type -> selección del revisor
const textos = ref<Record<string, string>>({}) // field_type -> valor tecleado en «otro valor…»
const anadidos = ref<string[]>([]) // campos del catálogo sobrescritos fuera de `fields`
const campoNuevo = ref('') // desplegable «añadir campo»

/** Atajos del drawer: `Enter` resuelve (equivale al botón primario), `Esc` cierra.
    Solo actúan con el drawer abierto y sin modificadores que indiquen otra intención. */
function onKeydown(e: KeyboardEvent) {
  if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey) return
  if (!props.invoiceId || !detail.value) return
  if (e.key === 'Escape') {
    emit('close')
  } else if (e.key === 'Enter' && !busy.value) {
    resolver()
  }
}
watch(
  () => props.invoiceId,
  async (id) => {
    detail.value = null
    error.value = ''
    elegidos.value = {}
    textos.value = {}
    anadidos.value = []
    campoNuevo.value = ''
    motivo.value = ''
    if (id) {
      // visible al instante: la carga del detalle puede tardar (PDF + decisión)
      cargando.value = true
      try {
        await load(id)
      } finally {
        cargando.value = false
      }
    }
  },
  { immediate: true }
)

onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => window.removeEventListener('keydown', onKeydown))

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

/** Campos listados: los del detalle (aunque no tengan candidatos) más los añadidos. */
const campos = computed<string[]>(() => {
  const propios = Object.keys(detail.value?.fields ?? {})
  return [...propios, ...anadidos.value.filter((f) => !propios.includes(f))]
})

/** Catálogo de campos que aún no están en pantalla (desplegable «añadir campo»). */
const catalogo = computed(() =>
  (detail.value?.supported_fields ?? []).filter((f) => !campos.value.includes(f))
)

function anadirCampo() {
  const f = campoNuevo.value
  campoNuevo.value = ''
  if (!f || campos.value.includes(f)) return
  anadidos.value = [...anadidos.value, f]
  elegir(f, { tipo: 'texto' }) // el campo añadido nace listo para teclear su valor
}

/** Selección vigente: por defecto el candidato líder (sin candidatos no elige nada). */
function seleccion(fieldType: string): Seleccion {
  return elegidos.value[fieldType] ?? { tipo: 'candidato', indice: liderIndex(candidatos(fieldType)) }
}

function elegir(fieldType: string, s: Seleccion) {
  elegidos.value = { ...elegidos.value, [fieldType]: s }
}

function elegido(fieldType: string): number {
  const s = seleccion(fieldType)
  return s.tipo === 'candidato' ? s.indice : -1
}

/** Texto libre tecleado para el campo (solo cuenta con «otro valor…» marcado). */
function textoDe(fieldType: string): string {
  return textos.value[fieldType] ?? ''
}

/** El backend ya dejó el campo sin valor (`after = null` en su último override). */
function descartadoPorElBackend(fieldType: string): boolean {
  return detail.value?.field_status?.[fieldType]?.discarded === true
}

/**
 * Cambio que enviaría la resolución para el campo (`null` = no cambia nada).
 * `accepted` sigue siendo «se mantiene el candidato líder»; cualquier otra
 * cosa (descarte, texto libre, otro candidato o restaurar un descartado) es
 * una corrección.
 */
function pendiente(fieldType: string): 'descartar' | 'texto' | 'valor' | null {
  const s = elegidos.value[fieldType]
  if (!s) return null
  if (s.tipo === 'descartar') return 'descartar'
  if (s.tipo === 'texto') return textoDe(fieldType).trim() ? 'texto' : null
  const cs = candidatos(fieldType)
  if (cs.length === 0) return null
  if (s.indice === liderIndex(cs)) return descartadoPorElBackend(fieldType) ? 'valor' : null
  return 'valor'
}

/** Estado honesto del campo: cambio pendiente o lo que ya hay en la base de datos. */
function estadoDe(fieldType: string): 'descartado' | 'corregido' | 'sin-valor' | '' {
  const p = pendiente(fieldType)
  if (p === 'descartar') return 'descartado'
  if (p !== null) return 'corregido'
  if (descartadoPorElBackend(fieldType)) return 'descartado'
  const st = detail.value?.field_status?.[fieldType]
  return st && !st.has_value ? 'sin-valor' : ''
}

const estados = computed<Record<string, string>>(() => {
  const out: Record<string, string> = {}
  for (const f of campos.value) out[f] = estadoDe(f)
  return out
})

const tieneCorreccion = computed(() => campos.value.some((f) => pendiente(f) !== null))

/**
 * Resuelve la revisión: confirma los campos cuyo candidato líder se mantiene
 * (`accepted`) y corrige los que el revisor cambia (`corrected`): otro
 * candidato, un texto libre o `null` para descartar el campo. Nunca se manda
 * el mismo campo en las dos listas. El backend recalcula la decisión de forma
 * determinista; nunca se fuerza el pago.
 */
async function resolver() {
  if (!detail.value || busy.value) return
  busy.value = true
  error.value = ''
  const d = detail.value
  const accepted: string[] = []
  const corrected: Record<string, unknown> = {}
  for (const fieldType of campos.value) {
    const cs = candidatos(fieldType)
    const cambio = pendiente(fieldType)
    if (cambio === 'descartar') {
      corrected[fieldType] = null // descartado: el motor lo ve sin valor
    } else if (cambio === 'texto') {
      corrected[fieldType] = textoDe(fieldType) // tal cual lo tecleado; el backend lo interpreta
    } else if (cambio === 'valor') {
      corrected[fieldType] = cs[elegido(fieldType)]?.value
    } else if (cs.length > 0 && !descartadoPorElBackend(fieldType)) {
      accepted.push(fieldType) // se confirma la lectura actual (before = after)
    }
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
    // Resuelta con éxito: la lista del padre se refresca (`updated`) y el
    // drawer se cierra solo; la acción terminó y no pide más clics.
    emit('updated')
    emit('close')
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

      <div v-if="cargando && !error" class="panel cargando" aria-live="polite">
        <span class="spinner"></span>
        <span>Cargando factura <span class="mono">{{ invoiceId }}</span>…</span>
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
            Todos los candidatos se conservan. Confirma el candidato correcto, descarta el campo
            con «(sin valor)» o escribe un valor propio con «otro valor…»; el backend registra la
            procedencia y recalcula la decisión con el mismo motor.
          </p>
          <div v-for="fieldType in campos" :key="fieldType" class="campo">
            <div class="campo-head">
              <strong class="mono">{{ fieldType }}</strong>
              <span
                v-if="estados[fieldType] === 'descartado'"
                class="badge disputa"
                title="El campo queda sin valor: la regla que lo consume no puede autorizar el pago"
              >
                descartado
              </span>
              <span v-else-if="estados[fieldType] === 'corregido'" class="badge ESCALAR">corregido</span>
              <span
                v-else-if="estados[fieldType] === 'sin-valor'"
                class="badge pendiente"
                title="El campo no tiene valor registrado"
              >
                sin valor
              </span>
              <span v-if="candidatos(fieldType).length === 0" class="muted">sin candidatos</span>
            </div>
            <label v-for="(c, i) in candidatos(fieldType)" :key="c.extractor + i" class="candidato">
              <input
                type="radio"
                :name="`cand-${fieldType}`"
                :checked="seleccion(fieldType).tipo === 'candidato' && elegido(fieldType) === i"
                @change="elegir(fieldType, { tipo: 'candidato', indice: i })"
              />
              <span class="mono">{{ fmtValor(c.value) }}</span>
              <span class="muted">· {{ c.extractor }} · {{ Math.round(c.confidence * 100) }}%</span>
            </label>
            <label class="candidato">
              <input
                type="radio"
                :name="`cand-${fieldType}`"
                :checked="seleccion(fieldType).tipo === 'descartar'"
                @change="elegir(fieldType, { tipo: 'descartar' })"
              />
              <span class="muted">(sin valor) · descarta el campo</span>
            </label>
            <label class="candidato">
              <input
                type="radio"
                :name="`cand-${fieldType}`"
                :checked="seleccion(fieldType).tipo === 'texto'"
                @change="elegir(fieldType, { tipo: 'texto' })"
              />
              <span class="muted">otro valor…</span>
            </label>
            <input
              v-if="seleccion(fieldType).tipo === 'texto'"
              v-model="textos[fieldType]"
              class="valor-libre"
              :aria-label="`Valor propio para ${fieldType}`"
              :placeholder="`valor para ${fieldType}…`"
            />
          </div>
          <p v-if="campos.length === 0" class="muted">sin campos extraídos</p>
          <div v-if="catalogo.length > 0" class="campo anadir">
            <div class="campo-head">
              <strong class="mono">añadir campo</strong>
              <span class="muted">del catálogo del sistema</span>
            </div>
            <select
              v-model="campoNuevo"
              aria-label="Campo del catálogo a sobrescribir"
              @change="anadirCampo"
            >
              <option value="">— elegir campo —</option>
              <option v-for="f in catalogo" :key="f" :value="f">{{ f }}</option>
            </select>
          </div>
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
.valor-libre { margin: 4px 0 0 12px; width: min(320px, 100%); }
.anadir { margin-top: 14px; }
.anadir select { max-width: 320px; }
.aplicar { margin-top: 10px; }
</style>
