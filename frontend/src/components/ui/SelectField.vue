<script setup lang="ts">
import { useId } from 'vue'

defineOptions({ inheritAttrs: false })
withDefaults(
  defineProps<{
    label: string
    options: { value: string; label: string }[]
    error?: string
    required?: boolean
    placeholder?: string
    hideLabel?: boolean
  }>(),
  { error: undefined, required: false, placeholder: undefined, hideLabel: false },
)
const model = defineModel<string | null>()
const id = useId()
</script>

<template>
  <div>
    <label :for="id" :class="hideLabel ? 'sr-only' : 'field-label'">{{ label }}<span v-if="required" class="text-red-600" aria-hidden="true"> *</span></label>
    <select
      :id="id"
      v-model="model"
      v-bind="$attrs"
      :required="required"
      class="field-input"
      :aria-invalid="error ? 'true' : undefined"
      :aria-describedby="error ? `${id}-error` : undefined"
    >
      <option v-if="placeholder !== undefined" :value="placeholder === '' ? '' : null" :disabled="required">{{ placeholder || 'Select…' }}</option>
      <option v-for="option in options" :key="option.value" :value="option.value">{{ option.label }}</option>
    </select>
    <p v-if="error" :id="`${id}-error`" class="mt-1 text-sm text-red-700">{{ error }}</p>
  </div>
</template>
