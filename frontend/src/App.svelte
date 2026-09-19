<script lang="ts">
  import Operaciones from './views/Operaciones.svelte'
  import Facturas from './views/Facturas.svelte'
  import Revision from './views/Revision.svelte'
  import Reglas from './views/Reglas.svelte'
  import Impacto from './views/Impacto.svelte'
  import Salud from './views/Salud.svelte'

  type Vista = 'operaciones' | 'facturas' | 'revision' | 'reglas' | 'impacto' | 'salud'
  let vista: Vista = $state('operaciones')

  const vistas: { id: Vista; etiqueta: string }[] = [
    { id: 'operaciones', etiqueta: 'Operaciones' },
    { id: 'facturas', etiqueta: 'Facturas' },
    { id: 'revision', etiqueta: 'Revisión' },
    { id: 'reglas', etiqueta: 'Reglas' },
    { id: 'impacto', etiqueta: 'Impacto' },
    { id: 'salud', etiqueta: 'Salud' }
  ]
</script>

<header>
  <h1>albertitos</h1>
  <nav>
    {#each vistas as v (v.id)}
      <a href="#{v.id}" class:active={vista === v.id} onclick={() => (vista = v.id)}>{v.etiqueta}</a>
    {/each}
  </nav>
</header>

<main>
  {#if vista === 'operaciones'}
    <Operaciones />
  {:else if vista === 'facturas'}
    <Facturas />
  {:else if vista === 'revision'}
    <Revision />
  {:else if vista === 'reglas'}
    <Reglas />
  {:else if vista === 'impacto'}
    <Impacto />
  {:else if vista === 'salud'}
    <Salud />
  {/if}
</main>
