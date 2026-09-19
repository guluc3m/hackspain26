<script lang="ts">
  import { api, type Factura, type Resultado } from '../lib/api'

  let facturas: Factura[] = $state([])
  let filtro = $state<'todos' | Resultado>('todos')

  $effect(() => {
    api.facturas().then((f) => (facturas = f)).catch(console.error)
  })

  const visibles = $derived(
    filtro === 'todos' ? facturas : facturas.filter((f) => f.result === filtro)
  )
</script>

<h2>Facturas</h2>
<p>
  Filtro:
  {#each ['todos', 'PAGAR', 'NO_PAGAR', 'ESCALAR'] as f}
    <label><input type="radio" bind:group={filtro} value={f} /> {f}</label>
  {/each}
</p>
<table>
  <thead>
    <tr><th>file_id</th><th>Resultado</th></tr>
  </thead>
  <tbody>
    {#each visibles as f (f.id)}
      <tr><td>{f.file_id}</td><td>{f.result ?? 'pendiente'}</td></tr>
    {/each}
  </tbody>
</table>
