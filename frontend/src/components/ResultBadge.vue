<script setup lang="ts">
import type { Resultado } from '../api'

defineProps<{ result: Resultado | null | undefined }>()
</script>

<template>
  <span v-if="result" class="badge" :class="result">{{ result }}</span>
  <span v-else class="badge pendiente">pendiente</span>
</template>
