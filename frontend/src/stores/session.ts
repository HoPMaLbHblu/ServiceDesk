import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { api } from '@/api/client'
import type { Session } from '@/api/types'
import { queryClient } from '@/lib/queryClient'

const EMPTY: Session = { authenticated: false, user: null, memberships: [], portal_links: [], active_workspace: null }

export const useSessionStore = defineStore('session', () => {
  const session = ref<Session>(EMPTY)
  const restored = ref(false)
  const expired = ref(false)

  const user = computed(() => session.value.user)
  const isAuthenticated = computed(() => session.value.authenticated)
  const workspace = computed(() => session.value.active_workspace)
  const workspaceId = computed(() => session.value.active_workspace?.id ?? null)
  const role = computed(() => session.value.active_workspace?.role ?? null)
  const isOwner = computed(() => role.value === 'owner')
  const isManager = computed(() => role.value === 'owner' || role.value === 'manager')
  const isTechnician = computed(() => role.value === 'technician')
  const memberships = computed(() => session.value.memberships)
  const hasPortal = computed(() => session.value.portal_links.length > 0)

  /**
   * Replace the session. Whenever the user or workspace changes, every cached
   * server record is dropped so another workspace's data can never be shown.
   */
  function apply(next: Session) {
    const previousUser = session.value.user?.id ?? null
    const previousWorkspace = session.value.active_workspace?.id ?? null
    session.value = next
    const userChanged = (next.user?.id ?? null) !== previousUser
    const workspaceChanged = (next.active_workspace?.id ?? null) !== previousWorkspace
    if (userChanged || workspaceChanged) queryClient.clear()
    if (next.authenticated) expired.value = false
  }

  async function restore() {
    try {
      apply(await api.get<Session>('/auth/session/'))
    } finally {
      restored.value = true
    }
  }

  async function login(email: string, password: string) {
    apply(await api.post<Session>('/auth/login/', { email, password }))
  }

  async function register(payload: { email: string; full_name: string; password: string }) {
    apply(await api.post<Session>('/auth/register/', payload))
  }

  async function logout() {
    try {
      await api.post('/auth/logout/')
    } finally {
      apply(EMPTY)
      queryClient.clear()
      // Refresh the CSRF cookie for the next login.
      await restore().catch(() => undefined)
    }
  }

  async function switchWorkspace(businessId: string) {
    apply(await api.post<Session>('/workspaces/switch/', { business_id: businessId }))
  }

  /** Called when any API request returns 401: the server session is gone. */
  function markExpired() {
    if (!session.value.authenticated) return
    apply(EMPTY)
    expired.value = true
  }

  return {
    session,
    restored,
    expired,
    user,
    isAuthenticated,
    workspace,
    workspaceId,
    role,
    isOwner,
    isManager,
    isTechnician,
    memberships,
    hasPortal,
    apply,
    restore,
    login,
    register,
    logout,
    switchWorkspace,
    markExpired,
  }
})
