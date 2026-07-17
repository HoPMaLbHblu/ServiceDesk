import { type Ref, onBeforeUnmount, onMounted } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'

const MESSAGE = 'You have unsaved changes. Leave this page and discard them?'

export function useUnsavedChanges(dirty: Ref<boolean>) {
  function beforeUnload(event: BeforeUnloadEvent) {
    if (!dirty.value) return
    event.preventDefault()
  }
  onMounted(() => window.addEventListener('beforeunload', beforeUnload))
  onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnload))
  onBeforeRouteLeave(() => (dirty.value ? window.confirm(MESSAGE) : true))
}
