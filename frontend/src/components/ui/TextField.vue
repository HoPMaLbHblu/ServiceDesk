<script setup lang="ts">
import { useId } from 'vue'

defineOptions({ inheritAttrs: false })

withDefaults(
  defineProps<{
    label: string
    error?: string
    hint?: string
    type?: string
    required?: boolean
    hideLabel?: boolean
  }>(),
  { type: 'text', error: undefined, hint: undefined, required: false, hideLabel: false },
)

const model = defineModel<string | number | null>()
const id = useId()
</script>

<template>
  <div>
    <label :for="id" :class="hideLabel ? 'sr-only' : 'field-label'">
      {{ label }}<span v-if="required" class="text-red-600" aria-hidden="true"> *</span>
    </label>
    <input
      :id="id"
      v-model="model"
      v-bind="$attrs"
      :type="type"
      :required="required"
      class="field-input"
      :aria-invalid="error ? 'true' : undefined"
      :aria-describedby="error ? `${id}-error` : hint ? `${id}-hint` : undefined"
    />
    <p v-if="error" :id="`${id}-error`" class="mt-1 text-sm text-red-700">{{ error }}</p>
    <p v-else-if="hint" :id="`${id}-hint`" class="mt-1 text-xs text-slate-500">{{ hint }}</p>
  </div>
</template>
