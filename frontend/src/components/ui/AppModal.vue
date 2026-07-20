<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, useId, watch } from 'vue'

/**
 * Modal built on the native <dialog> element, which provides focus trapping,
 * Escape to close and an inert background.
 */
const props = withDefaults(defineProps<{ open: boolean; title: string; size?: 'md' | 'lg' | 'xl' }>(), { size: 'md' })
const emit = defineEmits<{ close: [] }>()
const dialog = ref<HTMLDialogElement | null>(null)
const titleId = useId()
let opener: Element | null = null

watch(
  () => props.open,
  async (open) => {
    await nextTick()
    const el = dialog.value
    if (!el) return
    if (open && !el.open) {
      opener = document.activeElement
      el.showModal()
    } else if (!open && el.open) {
      el.close()
      if (opener instanceof HTMLElement) opener.focus()
    }
  },
  { immediate: true },
)

onBeforeUnmount(() => dialog.value?.open && dialog.value.close())

function onCancel(event: Event) {
  event.preventDefault()
  emit('close')
}

const widths = { md: 'max-w-lg', lg: 'max-w-2xl', xl: 'max-w-4xl' }
</script>

<template>
  <dialog
    ref="dialog"
    :aria-labelledby="titleId"
    :class="['w-[calc(100%-2rem)] rounded-lg p-0 shadow-xl backdrop:bg-slate-900/50', widths[size]]"
    @cancel="onCancel"
  >
    <div v-if="open" class="flex max-h-[85vh] flex-col">
      <header class="flex items-center justify-between border-b border-slate-200 px-5 py-3">
        <h2 :id="titleId" class="text-base font-semibold">{{ title }}</h2>
        <button type="button" class="rounded p-1 text-slate-500 hover:bg-slate-100" aria-label="Close" @click="emit('close')">
          <svg viewBox="0 0 20 20" class="h-5 w-5" aria-hidden="true"><path d="M5 5l10 10M15 5L5 15" stroke="currentColor" stroke-width="2" stroke-linecap="round" /></svg>
        </button>
      </header>
      <div class="overflow-y-auto px-5 py-4"><slot /></div>
      <footer v-if="$slots.footer" class="flex justify-end gap-2 border-t border-slate-200 bg-slate-50 px-5 py-3"><slot name="footer" /></footer>
    </div>
  </dialog>
</template>
