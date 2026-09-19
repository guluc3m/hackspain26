<script setup lang="ts">
import { ref } from 'vue'
import { SINTETICO } from './api'
import DashboardView from './views/DashboardView.vue'
import InvoicesView from './views/InvoicesView.vue'
import LogsView from './views/LogsView.vue'

type Tab = 'dashboard' | 'invoices' | 'logs'

const tab = ref<Tab>((() => {
  const h = window.location.hash.replace('#', '')
  return h === 'invoices' || h === 'logs' ? h : 'dashboard'
})())

const tabs: { id: Tab; label: string }[] = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'invoices', label: 'Invoices' },
  { id: 'logs', label: 'Logs' }
]

function go(t: Tab) {
  tab.value = t
  window.location.hash = t
}
</script>

<template>
  <header class="topbar">
    <nav>
      <button
        v-for="t in tabs"
        :key="t.id"
        class="tab"
        :class="{ active: tab === t.id }"
        @click="go(t.id)"
      >
        {{ t.label }}
      </button>
    </nav>
    <div
      class="modo"
      :title="SINTETICO ? 'Datos sintéticos de referencia (sin conexión real)' : 'Conexión real vacía: usa los targets *_syncth'"
    >
      {{ SINTETICO ? 'sintético' : 'sin conexión' }}
    </div>
    <!-- bloque reservado para el logo -->
    <div class="logo-box" title="albertitos">
      <img src="/logo.svg" alt="logo" />
    </div>
  </header>

  <main>
    <DashboardView v-if="tab === 'dashboard'" />
    <InvoicesView v-else-if="tab === 'invoices'" />
    <LogsView v-else />
  </main>
</template>

<style scoped>
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--panel);
  border-bottom: 1px solid var(--border);
  padding: 0 20px;
}
nav { display: flex; gap: 4px; }
.tab {
  border: none;
  border-radius: 0;
  background: none;
  padding: 16px 12px 14px;
  font-size: 15px;
  color: var(--muted);
  border-bottom: 2px solid transparent;
}
.tab:hover { background: none; color: var(--text); }
.tab.active {
  color: var(--text);
  font-weight: 600;
  border-bottom-color: var(--accent);
}
.logo-box {
  width: 36px;
  height: 36px;
  border-radius: 6px;
  background: #1c3144;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  flex: none;
}
.logo-box img { width: 30px; height: 30px; object-fit: contain; }
.modo {
  font-size: 12px;
  color: var(--muted);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 2px 10px;
  margin-right: 10px;
}
main { max-width: 1100px; margin: 0 auto; padding: 20px; }
</style>
