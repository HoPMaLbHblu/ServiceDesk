<script setup lang="ts">
defineProps<{ title: string; subtitle?: string }>()
</script>

<template>
  <div class="mb-5 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
    <div class="min-w-0">
      <slot name="breadcrumb" />
      <h1 class="text-xl font-semibold tracking-tight text-slate-900 sm:text-2xl">{{ title }}</h1>
      <p v-if="subtitle" class="mt-1 text-sm text-slate-600">{{ subtitle }}</p>
      <slot name="meta" />
    </div>
    <div v-if="$slots.actions" class="flex flex-wrap gap-2">
      <slot name="actions" />
    </div>
  </div>
</template>
