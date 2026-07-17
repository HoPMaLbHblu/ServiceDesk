import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

/** UI preferences only. Business records are never written to local storage. */
const KEY = 'servicedesk.ui'

interface Preferences {
  sidebarCollapsed: boolean
  ordersPageSize: number
}

function load(): Preferences {
  try {
    const raw = localStorage.getItem(KEY)
    if (raw) return { sidebarCollapsed: false, ordersPageSize: 25, ...(JSON.parse(raw) as Partial<Preferences>) }
  } catch {
    /* storage unavailable: use defaults */
  }
  return { sidebarCollapsed: false, ordersPageSize: 25 }
}

export const useUiStore = defineStore('ui', () => {
  const preferences = ref<Preferences>(load())
  const mobileNavOpen = ref(false)

  watch(
    preferences,
    (value) => {
      try {
        localStorage.setItem(KEY, JSON.stringify(value))
      } catch {
        /* ignore */
      }
    },
    { deep: true },
  )

  return { preferences, mobileNavOpen }
})
