<script setup lang="ts">
import { computed } from 'vue'

import type { Role } from '@/api/types'
import PageHeader from '@/components/ui/PageHeader.vue'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()
const TABS: { name: string; label: string; roles?: Role[] }[] = [
  { name: 'settings-account', label: 'Account' },
  { name: 'settings-business', label: 'Business', roles: ['owner'] },
  { name: 'settings-team', label: 'Team', roles: ['owner'] },
  { name: 'settings-schedule', label: 'Working hours', roles: ['owner', 'manager'] },
  { name: 'settings-billing', label: 'Billing' },
  { name: 'settings-notifications', label: 'Email outbox', roles: ['owner', 'manager'] },
  { name: 'settings-audit', label: 'Audit log', roles: ['owner'] },
]
const tabs = computed(() => TABS.filter((t) => !t.roles || t.roles.includes(session.role as Role)))
</script>

<template>
  <div>
    <PageHeader title="Settings" />
    <nav class="mb-6 -mx-1 flex gap-1 overflow-x-auto border-b border-slate-200" aria-label="Settings sections">
      <RouterLink
        v-for="t in tabs"
        :key="t.name"
        :to="{ name: t.name }"
        class="shrink-0 border-b-2 border-transparent px-3 py-2 text-sm whitespace-nowrap text-slate-600 hover:text-slate-900"
        active-class="!border-brand-600 font-medium !text-slate-900"
      >
        {{ t.label }}
      </RouterLink>
    </nav>
    <RouterView />
  </div>
</template>
