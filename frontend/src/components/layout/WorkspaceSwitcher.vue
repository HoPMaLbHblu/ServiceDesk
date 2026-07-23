<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import { ApiError } from '@/api/client'
import { useSessionStore } from '@/stores/session'
import { useToastStore } from '@/stores/toasts'

const session = useSessionStore()
const toasts = useToastStore()
const router = useRouter()
const switching = ref(false)

const selected = computed({
  get: () => session.workspaceId ?? '',
  set: (value: string) => void choose(value),
})

async function choose(businessId: string) {
  if (businessId === '__new') {
    await router.push({ name: 'welcome', query: { create: '1' } })
    return
  }
  if (!businessId || businessId === session.workspaceId) return
  switching.value = true
  try {
    await session.switchWorkspace(businessId)
    // Records of the previous workspace are not valid here; start from the home screen.
    await router.push({ name: 'dashboard' })
    toasts.info(`Switched to ${session.workspace?.name}`)
  } catch (error) {
    toasts.error(error instanceof ApiError ? error.message : 'Could not switch workspace.')
  } finally {
    switching.value = false
  }
}
</script>

<template>
  <div>
    <label for="workspace-switcher" class="mb-1 block text-xs font-medium tracking-wide text-slate-400 uppercase">Workspace</label>
    <select
      id="workspace-switcher"
      v-model="selected"
      :disabled="switching"
      data-testid="workspace-switcher"
      class="block w-full rounded-md border border-slate-700 bg-slate-800 px-2 py-1.5 text-sm text-white focus:border-brand-600 focus:outline-none"
    >
      <option v-for="m in session.memberships" :key="m.business_id" :value="m.business_id">{{ m.business_name }} ({{ m.role }})</option>
      <option value="__new">+ Create another workspace</option>
    </select>
  </div>
</template>
