<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'
import { computed } from 'vue'

import { ApiError, api } from '@/api/client'
import { useInvalidateWorkspace, useSubscription, useWorkspaceQueryKey } from '@/api/queries'
import type { Invitation, Member } from '@/api/types'
import AppButton from '@/components/ui/AppButton.vue'
import FormAlert from '@/components/ui/FormAlert.vue'
import SelectField from '@/components/ui/SelectField.vue'
import TextField from '@/components/ui/TextField.vue'
import { useApiForm } from '@/composables/useApiForm'
import { useConfirm } from '@/composables/useConfirm'
import { date } from '@/lib/format'
import { useSessionStore } from '@/stores/session'
import { useToastStore } from '@/stores/toasts'

const session = useSessionStore()
const toasts = useToastStore()
const confirm = useConfirm()
const invalidate = useInvalidateWorkspace()
const subscription = useSubscription()

const members = useQuery({ queryKey: useWorkspaceQueryKey('members'), queryFn: () => api.get<Member[]>('/members/', { is_active: true }) })
const invitations = useQuery({ queryKey: useWorkspaceQueryKey('invitations'), queryFn: () => api.get<Invitation[]>('/invitations/') })
const pending = computed(() => (invitations.data.value ?? []).filter((i) => i.status === 'pending'))
const roles = [
  { value: 'owner', label: 'Owner' },
  { value: 'manager', label: 'Manager' },
  { value: 'technician', label: 'Technician' },
]
const limit = computed(() => subscription.data.value?.plan?.max_staff ?? null)

const invite = useApiForm({ email: '', role: 'technician' })
async function sendInvite() {
  const ok = await invite.submit((v) => api.post('/invitations/', v))
  if (ok) {
    toasts.success(`Invitation sent to ${invite.values.email}`)
    invite.reset({ email: '', role: 'technician' })
    await invalidate()
  }
}

async function changeRole(member: Member, role: string) {
  if (role === member.role) return
  try {
    await api.post(`/members/${member.id}/change_role/`, { role })
    toasts.success(`${member.full_name} is now ${role}`)
    if (member.user_id === session.user?.id) await session.restore()
  } catch (e) {
    toasts.error(e instanceof ApiError ? e.message : 'Could not change the role.')
  } finally {
    await invalidate()
  }
}

async function remove(member: Member) {
  const ok = await confirm({
    title: `Remove ${member.full_name}?`,
    message: 'They lose access to this workspace immediately. Their past work stays in the records.',
    confirmLabel: 'Remove',
    danger: true,
  })
  if (!ok) return
  try {
    await api.post(`/members/${member.id}/deactivate/`)
    toasts.success(`${member.full_name} removed`)
  } catch (e) {
    toasts.error(e instanceof ApiError ? e.message : 'Could not remove the member.')
  } finally {
    await invalidate()
  }
}

async function revoke(invitation: Invitation) {
  try {
    await api.post(`/invitations/${invitation.id}/revoke/`)
  } catch (e) {
    toasts.error(e instanceof ApiError ? e.message : 'Could not revoke.')
  } finally {
    await invalidate()
  }
}
</script>

<template>
  <div class="grid max-w-4xl gap-6">
    <section class="card overflow-hidden">
      <div class="flex items-center justify-between px-5 pt-5 pb-3">
        <h2 class="font-semibold">Team members</h2>
        <span v-if="limit" class="text-sm text-slate-500">{{ (members.data.value?.length ?? 0) + pending.length }} of {{ limit }} seats used</span>
      </div>
      <ul class="divide-y divide-slate-100">
        <li v-for="m in members.data.value ?? []" :key="m.id" class="flex flex-wrap items-center justify-between gap-3 px-5 py-3 text-sm">
          <div>
            <p class="font-medium">{{ m.full_name }} <span v-if="m.user_id === session.user?.id" class="font-normal text-slate-500">(you)</span></p>
            <p class="text-slate-500">{{ m.email }}</p>
          </div>
          <div class="flex items-center gap-2">
            <select :value="m.role" class="field-input w-auto" :aria-label="`Role of ${m.full_name}`" @change="changeRole(m, ($event.target as HTMLSelectElement).value)">
              <option v-for="r in roles" :key="r.value" :value="r.value">{{ r.label }}</option>
            </select>
            <AppButton size="sm" variant="ghost" class="text-red-700" @click="remove(m)">Remove</AppButton>
          </div>
        </li>
      </ul>
    </section>

    <section class="card p-5">
      <h2 class="font-semibold">Invite someone</h2>
      <p class="mt-1 text-sm text-slate-600">Managers run the front desk, estimates, invoices and stock. Technicians see only the repairs assigned to them.</p>
      <form class="mt-4 flex flex-col gap-3 sm:flex-row sm:items-start" novalidate @submit.prevent="sendInvite">
        <TextField v-model="invite.values.email" class="flex-1" label="Email" type="email" required :error="invite.fieldError('email')" />
        <SelectField v-model="invite.values.role" label="Role" :options="roles" :error="invite.fieldError('role')" />
        <AppButton type="submit" class="sm:mt-6" :loading="invite.submitting.value">Send invitation</AppButton>
      </form>
      <FormAlert class="mt-3" :message="invite.generalError.value">
        <RouterLink v-if="invite.generalError.value?.includes('plan')" :to="{ name: 'settings-billing' }" class="ml-1 underline">Change plan</RouterLink>
      </FormAlert>
      <div v-if="pending.length" class="mt-5">
        <h3 class="text-sm font-medium">Pending invitations</h3>
        <ul class="mt-2 divide-y divide-slate-100 text-sm">
          <li v-for="i in pending" :key="i.id" class="flex items-center justify-between py-2">
            <span>{{ i.email }} · {{ i.role }} <span class="text-slate-500">· expires {{ date(i.expires_at) }}</span></span>
            <button type="button" class="text-red-700 hover:underline" @click="revoke(i)">Revoke</button>
          </li>
        </ul>
      </div>
    </section>
  </div>
</template>
