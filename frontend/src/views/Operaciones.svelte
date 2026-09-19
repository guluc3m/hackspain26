<script lang="ts">
  import { api, type Factura } from '../lib/api'

  let facturas: Factura[] = $state([])
  let error = $state('')

  $effect(() => {
    api
      .facturas()
      .then((f) => (facturas = f))
      .catch((e) => (error = String(e)))
  })
</script>

<h2>Operaciones</h2>
<p>Pipeline en ejecución: estado del lote, resumable e idempotente.</p>
{#if error}
  <p class="error">{error}</p>
{:else}
  <p>Facturas vistas: {facturas.length}</p>
  <ul>
    {#each facturas as f (f.id)}
      <li>{f.file_id} — {f.result ?? 'pendiente'}</li>
    {/each}
  </ul>
{/if}
