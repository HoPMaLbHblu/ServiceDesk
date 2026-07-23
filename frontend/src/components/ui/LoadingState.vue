<script setup lang="ts">
import AppSpinner from './AppSpinner.vue'

withDefaults(defineProps<{ label?: string }>(), { label: 'Loading…' })
</script>

<template>
  <div class="flex items-center justify-center gap-2 py-10 text-sm text-slate-500" role="status">
    <AppSpinner class="h-5 w-5" />
    <span>{{ label }}</span>
  </div>
</template>
