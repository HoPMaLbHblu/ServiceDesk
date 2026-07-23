<script setup lang="ts">
import { useToastStore } from '@/stores/toasts'

const toasts = useToastStore()
const tones = {
  success: 'border-green-300 bg-green-50 text-green-900',
  error: 'border-red-300 bg-red-50 text-red-900',
  info: 'border-slate-300 bg-white text-slate-900',
}
</script>

<template>
  <div class="pointer-events-none fixed inset-x-0 bottom-0 z-50 flex flex-col items-center gap-2 p-4 sm:items-end" aria-live="polite">
    <div
      v-for="toast in toasts.toasts"
      :key="toast.id"
      :role="toast.kind === 'error' ? 'alert' : 'status'"
      :class="['pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-md border px-4 py-3 text-sm shadow-lg', tones[toast.kind]]"
    >
      <p class="flex-1">{{ toast.message }}</p>
      <button type="button" class="text-slate-500 hover:text-slate-800" aria-label="Dismiss" @click="toasts.dismiss(toast.id)">×</button>
    </div>
  </div>
</template>
