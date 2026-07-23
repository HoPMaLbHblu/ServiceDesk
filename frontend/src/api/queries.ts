/** Shared queries used by several screens. Every key is scoped to the active workspace. */
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed } from 'vue'

import { useSessionStore } from '@/stores/session'

import { api } from './client'
import type { Business, StaffOption, SubscriptionState } from './types'

export function useWorkspaceQueryKey(...parts: unknown[]) {
  const session = useSessionStore()
  return computed(() => ['ws', session.workspaceId, ...parts])
}

export function useStaffOptions() {
  const session = useSessionStore()
  return useQuery({
    queryKey: useWorkspaceQueryKey('staff-options'),
    queryFn: () => api.get<StaffOption[]>('/members/staff_options/'),
    enabled: computed(() => !!session.workspaceId),
    staleTime: 60_000,
  })
}

export function useSubscription() {
  const session = useSessionStore()
  return useQuery({
    queryKey: useWorkspaceQueryKey('subscription'),
    queryFn: () => api.get<SubscriptionState>('/billing/subscription/'),
    enabled: computed(() => !!session.workspaceId),
    staleTime: 60_000,
  })
}

export function useBusiness() {
  const session = useSessionStore()
  return useQuery({
    queryKey: useWorkspaceQueryKey('business'),
    queryFn: () => api.get<Business>('/business/'),
    enabled: computed(() => !!session.workspaceId),
  })
}

/**
 * Refresh workspace data after a change. Mutations touch several screens at once
 * (an order change moves stock, invoices and the timeline), so every active
 * query of the workspace is refetched; inactive ones are marked stale.
 */
export function useInvalidateWorkspace() {
  const queryClient = useQueryClient()
  const session = useSessionStore()
  return () => queryClient.invalidateQueries({ queryKey: ['ws', session.workspaceId] })
}
