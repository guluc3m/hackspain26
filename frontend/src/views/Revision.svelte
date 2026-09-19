<script lang="ts">
  import { api } from '../lib/api'

  let invoiceId = $state('')
  let detalle = $state<Record<string, unknown> | null>(null)
  let error = $state('')

  async function cargar() {
    error = ''
    try {
      detalle = await api.factura(invoiceId)
    } catch (e) {
      error = String(e)
    }
  }

  async function guardarOverride(campo: string, valorActual: unknown) {
    const after = prompt(`Nuevo valor para ${campo}`, String(valorActual))
    if (after === null) return
    await fetch(`/api/revision/${invoiceId}/override`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        field_type: campo,
        before: valorActual,
        after,
        who: 'revisor',
        rung: 'review-ui',
        reason: 'corrección manual en revisión'
      })
    })
    await cargar()
  }
</script>

<h2>Revisión</h2>
<p>
  Cola de escalados: página y todos los candidatos lado a lado. Un override
  afecta solo a la extracción; la decisión se recalcula con el mismo motor.
</p>
<input placeholder="invoice_id" bind:value={invoiceId} />
<button onclick={cargar}>Cargar</button>
{#if error}
  <p class="error">{error}</p>
{/if}
{#if detalle}
  <pre>{JSON.stringify(detalle, null, 2)}</pre>
{/if}
