import { VueQueryPlugin } from '@tanstack/vue-query'
import { createPinia } from 'pinia'
import { createApp } from 'vue'

import { onUnauthorized } from '@/api/client'
import { queryClient } from '@/lib/queryClient'
import { router } from '@/router'
import { useSessionStore } from '@/stores/session'

import App from './App.vue'
import './styles.css'

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)
app.use(VueQueryPlugin, { queryClient })
app.use(router)

// A 401 from any API call means the server session ended (logout elsewhere,
// expiry, password change). Drop all cached data and send the user to sign in.
onUnauthorized(() => {
  const session = useSessionStore(pinia)
  if (!session.isAuthenticated) return
  session.markExpired()
  const current = router.currentRoute.value
  if (!current.meta.public) {
    void router.replace({ name: 'login', query: { next: current.fullPath, expired: '1' } })
  }
})

app.mount('#app')
