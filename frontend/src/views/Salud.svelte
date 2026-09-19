<script lang="ts">
  import { api } from '../lib/api'

  let salud: Record<string, string> | null = $state(null)

  $effect(() => {
    api.salud().then((s) => (salud = s)).catch(console.error)
  })
</script>

<h2>Salud</h2>
{#if salud}
  <ul>
    {#each Object.entries(salud) as [k, v] (k)}
      <li><strong>{k}</strong>: {v}</li>
    {/each}
  </ul>
{:else}
  <p>Cargando…</p>
{/if}
