import { VueQueryPlugin } from '@tanstack/vue-query'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import type { Component } from 'vue'

import { queryClient } from '@/lib/queryClient'
import { createAppRouter } from '@/router'
import { useSessionStore } from '@/stores/session'

import { sessionFor } from './fetch'

/** Mount with the real router, Pinia and query client, signed in with the given role. */
export async function mountAs(role: 'owner' | 'manager' | 'technician' | null, component: Component, props: Record<string, unknown> = {}, path = '/') {
  const pinia = createPinia()
  setActivePinia(pinia)
  queryClient.clear()
  const session = useSessionStore()
  if (role) session.apply(sessionFor(role))
  session.restored = true
  const router = createAppRouter()
  await router.replace(path).catch(() => undefined)
  const wrapper = mount(component, {
    props,
    attachTo: document.body,
    global: { plugins: [pinia, [VueQueryPlugin, { queryClient }], router] },
  })
  return { wrapper, session, router }
}

export const flush = () => new Promise((resolve) => setTimeout(resolve, 0))
