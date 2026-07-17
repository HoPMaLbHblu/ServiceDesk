import { computed } from 'vue'

import { useSessionStore } from '@/stores/session'

/**
 * Query keys for workspace data always start with the active business id, so a
 * cached record of one workspace is never reused for another.
 */
export function useTenantKey() {
  const session = useSessionStore()
  return (...parts: unknown[]) => computed(() => ['ws', session.workspaceId, ...parts])
}

export function tenantKeyPrefix(workspaceId: string | null) {
  return ['ws', workspaceId]
}
