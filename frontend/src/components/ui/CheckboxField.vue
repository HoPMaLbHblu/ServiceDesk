<script setup lang="ts">
import { useId } from 'vue'

defineProps<{ label: string; hint?: string }>()
const model = defineModel<boolean>()
const id = useId()
</script>

<template>
  <div class="flex items-start gap-2">
    <input :id="id" v-model="model" type="checkbox" class="mt-0.5 h-4 w-4 rounded border-slate-300 text-brand-600" />
    <label :for="id" class="text-sm text-slate-700">
      {{ label }}
      <span v-if="hint" class="block text-xs text-slate-500">{{ hint }}</span>
    </label>
  </div>
</template>
