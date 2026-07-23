<script setup lang="ts">
defineProps<{ title: string; description?: string }>()
</script>

<template>
  <div class="flex flex-col items-center justify-center px-4 py-10 text-center">
    <svg viewBox="0 0 24 24" class="h-10 w-10 text-slate-300" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
      <path d="M3 7l9-4 9 4-9 4-9-4zm0 0v10l9 4 9-4V7" stroke-linejoin="round" />
    </svg>
    <p class="mt-3 text-sm font-medium text-slate-900">{{ title }}</p>
    <p v-if="description" class="mt-1 max-w-sm text-sm text-slate-600">{{ description }}</p>
    <div v-if="$slots.default" class="mt-4"><slot /></div>
  </div>
</template>
