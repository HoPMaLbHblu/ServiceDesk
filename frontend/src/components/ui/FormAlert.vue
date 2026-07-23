<script setup lang="ts">
withDefaults(defineProps<{ message: string | null | undefined; tone?: 'error' | 'info' | 'success' | 'warning' }>(), { tone: 'error' })

const tones = {
  error: 'border-red-200 bg-red-50 text-red-800',
  info: 'border-blue-200 bg-blue-50 text-blue-900',
  success: 'border-green-200 bg-green-50 text-green-800',
  warning: 'border-amber-200 bg-amber-50 text-amber-900',
}
</script>

<template>
  <div v-if="message" :role="tone === 'error' ? 'alert' : 'status'" :class="['rounded-md border px-3 py-2 text-sm', tones[tone]]">
    {{ message }}
    <slot />
  </div>
</template>
