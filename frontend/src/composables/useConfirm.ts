import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface ConfirmOptions {
  title: string
  message: string
  confirmLabel?: string
  danger?: boolean
}

export const useConfirmStore = defineStore('confirm', () => {
  const current = ref<(ConfirmOptions & { resolve: (ok: boolean) => void }) | null>(null)

  function ask(options: ConfirmOptions): Promise<boolean> {
    return new Promise((resolve) => {
      current.value = { ...options, resolve }
    })
  }

  function answer(ok: boolean) {
    current.value?.resolve(ok)
    current.value = null
  }

  return { current, ask, answer }
})

/** Ask the user to confirm a consequential action. */
export function useConfirm() {
  return useConfirmStore().ask
}
