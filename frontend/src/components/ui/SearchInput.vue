<script setup lang="ts">
withDefaults(defineProps<{ label?: string; placeholder?: string }>(), { label: 'Search', placeholder: 'Search…' })
const model = defineModel<string>({ default: '' })
</script>

<template>
  <div class="relative w-full sm:max-w-xs">
    <label class="sr-only" :for="`search-${label}`">{{ label }}</label>
    <svg viewBox="0 0 20 20" class="pointer-events-none absolute top-2.5 left-2.5 h-4 w-4 text-slate-400" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
      <circle cx="9" cy="9" r="6" /><path d="M14 14l4 4" stroke-linecap="round" />
    </svg>
    <input :id="`search-${label}`" v-model="model" type="search" class="field-input pl-8" :placeholder="placeholder" />
  </div>
</template>
