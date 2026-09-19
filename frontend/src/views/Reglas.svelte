<script lang="ts">
  import { api, type Reglas } from '../lib/api'

  let reglas: Reglas | null = $state(null)

  $effect(() => {
    api.reglas().then((r) => (reglas = r)).catch(console.error)
  })
</script>

<h2>Reglas</h2>
{#if reglas}
  <p>
    Conjunto <strong>{reglas.rule_set_version}</strong> · config
    <code>{reglas.config_version}</code>
  </p>
  <ul>
    {#each reglas.enabled as codigo (codigo)}
      <li>
        <strong>{codigo}</strong>
        {#if reglas.thresholds[codigo]}
          — {JSON.stringify(reglas.thresholds[codigo])}
        {/if}
      </li>
    {/each}
  </ul>
{:else}
  <p>Cargando…</p>
{/if}
