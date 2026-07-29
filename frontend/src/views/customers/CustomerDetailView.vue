<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'
import { computed, ref } from 'vue'

import { ApiError, api } from '@/api/client'
import { useInvalidateWorkspace, useWorkspaceQueryKey } from '@/api/queries'
import type { Customer, CustomerNote, Device, OrderList, Paginated, PortalAccess } from '@/api/types'
import CustomerFormModal from '@/components/customers/CustomerFormModal.vue'
import DeviceFormModal from '@/components/customers/DeviceFormModal.vue'
import AppButton from '@/components/ui/AppButton.vue'
import DescriptionList from '@/components/ui/DescriptionList.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import ErrorState from '@/components/ui/ErrorState.vue'
import FormAlert from '@/components/ui/FormAlert.vue'
import LoadingState from '@/components/ui/LoadingState.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import TextAreaField from '@/components/ui/TextAreaField.vue'
import TextField from '@/components/ui/TextField.vue'
import { useApiForm } from '@/composables/useApiForm'
import { useConfirm } from '@/composables/useConfirm'
import { date, dateTime } from '@/lib/format'
import { useSessionStore } from '@/stores/session'
import { useToastStore } from '@/stores/toasts'

const props = defineProps<{ id: string }>()
const session = useSessionStore()
const toasts = useToastStore()
const confirm = useConfirm()
const invalidate = useInvalidateWorkspace()

const customer = useQuery({
  queryKey: useWorkspaceQueryKey('customer', props.id),
  queryFn: () => api.get<Customer>(`/customers/${props.id}/`),
})
const devices = useQuery({
  queryKey: useWorkspaceQueryKey('customer', props.id, 'devices'),
  queryFn: () => api.get<Device[]>(`/customers/${props.id}/devices/`),
})
const orders = useQuery({
  queryKey: useWorkspaceQueryKey('orders', { customer: props.id }),
  queryFn: () => api.get<Paginated<OrderList>>('/orders/', { customer: props.id, page_size: 50 }),
})
const notes = useQuery({
  queryKey: useWorkspaceQueryKey('customer', props.id, 'notes'),
  queryFn: () => api.get<CustomerNote[]>(`/customers/${props.id}/notes/`),
})
const portal = useQuery({
  queryKey: useWorkspaceQueryKey('customer', props.id, 'portal'),
  queryFn: () => api.get<PortalAccess[]>(`/customers/${props.id}/portal_access/`),
  enabled: computed(() => session.isManager),
})

const editing = ref(false)
const deviceModal = ref<{ open: boolean; device: Device | null }>({ open: false, device: null })

const noteForm = useApiForm({ body: '' })
async function addNote() {
  const ok = await noteForm.submit((v) => api.post(`/customers/${props.id}/notes/`, v))
  if (ok) {
    noteForm.reset({ body: '' })
    await invalidate()
  }
}

const inviteForm = useApiForm({ email: '' })
async function invite() {
  const ok = await inviteForm.submit(async (v) => {
    await api.post(`/customers/${props.id}/invite_to_portal/`, v)
    return true
  })
  if (ok) {
    toasts.success(`Portal invitation sent to ${inviteForm.values.email}`)
    inviteForm.reset({ email: '' })
  }
}

async function revoke(access: PortalAccess) {
  if (!(await confirm({ title: 'Remove portal access?', message: `${access.email} will no longer see this customer's repairs.`, confirmLabel: 'Remove', danger: true }))) return
  try {
    await api.post(`/customers/${props.id}/revoke_portal/`, { access_id: access.id })
    await invalidate()
  } catch (error) {
    toasts.error(error instanceof ApiError ? error.message : 'Could not remove access.')
  }
}

async function toggleArchive() {
  const c = customer.data.value
  if (!c) return
  try {
    await api.patch(`/customers/${props.id}/`, { is_archived: !c.is_archived })
    await invalidate()
    toasts.success(c.is_archived ? 'Customer restored' : 'Customer archived')
  } catch (error) {
    toasts.error(error instanceof ApiError ? error.message : 'Could not update the customer.')
  }
}
</script>

<template>
  <div>
    <LoadingState v-if="customer.isPending.value" />
    <ErrorState v-else-if="customer.isError.value" :error="customer.error.value" />
    <template v-else-if="customer.data.value">
      <PageHeader :title="customer.data.value.full_name" :subtitle="customer.data.value.company || undefined">
        <template #breadcrumb>
          <RouterLink :to="{ name: 'customers' }" class="text-sm text-slate-500 hover:underline">← Customers</RouterLink>
        </template>
        <template v-if="session.isManager" #actions>
          <RouterLink :to="{ name: 'order-new', query: { customer: id } }" class="rounded-md bg-brand-600 px-3.5 py-2 text-sm font-medium text-white hover:bg-brand-700">New order</RouterLink>
          <AppButton variant="secondary" @click="editing = true">Edit</AppButton>
          <AppButton variant="ghost" @click="toggleArchive">{{ customer.data.value.is_archived ? 'Restore' : 'Archive' }}</AppButton>
        </template>
      </PageHeader>

      <FormAlert v-if="customer.data.value.is_archived" class="mb-4" tone="warning" message="This customer is archived. Existing records stay available." />

      <div class="grid gap-6 lg:grid-cols-3">
        <div class="space-y-6 lg:col-span-2">
          <section class="card p-4">
            <h2 class="mb-3 font-semibold">Contact</h2>
            <DescriptionList
              :items="[
                { label: 'Phone', value: customer.data.value.phone },
                { label: 'Email', value: customer.data.value.email },
                { label: 'Address', value: customer.data.value.address },
                { label: 'Customer since', value: date(customer.data.value.created_at) },
                { label: 'Notes', value: customer.data.value.customer_notes },
                { label: 'Marketing emails', value: customer.data.value.marketing_opt_in ? 'Opted in' : 'No' },
              ]"
            />
          </section>

          <section class="card">
            <div class="flex items-center justify-between border-b border-slate-200 px-4 py-3">
              <h2 class="font-semibold">Devices</h2>
              <AppButton v-if="session.isManager" size="sm" variant="secondary" @click="deviceModal = { open: true, device: null }">Add device</AppButton>
            </div>
            <LoadingState v-if="devices.isPending.value" />
            <EmptyState v-else-if="!devices.data.value?.length" title="No devices yet" />
            <ul v-else class="divide-y divide-slate-100">
              <li v-for="d in devices.data.value" :key="d.id" class="flex items-start justify-between gap-3 px-4 py-3 text-sm">
                <div>
                  <p class="font-medium">{{ d.label }}</p>
                  <p class="text-slate-500">
                    <span v-if="d.serial_number">S/N {{ d.serial_number }}</span><span v-if="d.imei"> · IMEI {{ d.imei }}</span><span v-if="d.color"> · {{ d.color }}</span>
                  </p>
                </div>
                <AppButton v-if="session.isManager" size="sm" variant="ghost" @click="deviceModal = { open: true, device: d }">Edit</AppButton>
              </li>
            </ul>
          </section>

          <section class="card">
            <h2 class="border-b border-slate-200 px-4 py-3 font-semibold">Repair history</h2>
            <LoadingState v-if="orders.isPending.value" />
            <EmptyState v-else-if="!orders.data.value?.results.length" title="No repair orders yet" />
            <ul v-else class="divide-y divide-slate-100">
              <li v-for="o in orders.data.value.results" :key="o.id">
                <RouterLink :to="{ name: 'order', params: { id: o.id } }" class="flex items-center justify-between gap-3 px-4 py-3 text-sm hover:bg-slate-50">
                  <div class="min-w-0">
                    <p class="font-medium">{{ o.reference }} · {{ o.device_label }}</p>
                    <p class="text-slate-500">{{ date(o.created_at) }}</p>
                  </div>
                  <StatusBadge :status="o.status ?? 'new'" />
                </RouterLink>
              </li>
            </ul>
          </section>
        </div>

        <div class="space-y-6">
          <section class="card p-4">
            <h2 class="mb-3 font-semibold">Internal notes</h2>
            <form v-if="session.isManager" class="mb-4 space-y-2" @submit.prevent="addNote">
              <TextAreaField v-model="noteForm.values.body" label="Add a note" :rows="2" :error="noteForm.fieldError('body')" />
              <AppButton type="submit" size="sm" :loading="noteForm.submitting.value" :disabled="!noteForm.values.body.trim()">Add note</AppButton>
            </form>
            <p v-if="!notes.data.value?.length" class="text-sm text-slate-500">No notes.</p>
            <ul v-else class="space-y-3">
              <li v-for="n in notes.data.value" :key="n.id" class="text-sm">
                <p class="whitespace-pre-line">{{ n.body }}</p>
                <p class="mt-0.5 text-xs text-slate-500">{{ n.author_name }} · {{ dateTime(n.created_at) }}</p>
              </li>
            </ul>
          </section>

          <section v-if="session.isManager" class="card p-4">
            <h2 class="font-semibold">Customer portal</h2>
            <p class="mt-1 text-sm text-slate-600">Let the customer follow repairs, approve estimates and download invoices online.</p>
            <ul v-if="portal.data.value?.length" class="mt-3 space-y-2">
              <li v-for="a in portal.data.value" :key="a.id" class="flex items-center justify-between text-sm">
                <span>{{ a.email }}</span>
                <button type="button" class="text-red-700 hover:underline" @click="revoke(a)">Remove</button>
              </li>
            </ul>
            <form class="mt-3 space-y-2" novalidate @submit.prevent="invite">
              <FormAlert :message="inviteForm.generalError.value" />
              <TextField v-model="inviteForm.values.email" label="Invite by email" type="email" :placeholder="customer.data.value.email" :error="inviteForm.fieldError('email')" />
              <AppButton type="submit" size="sm" variant="secondary" :loading="inviteForm.submitting.value">Send invitation</AppButton>
            </form>
          </section>
        </div>
      </div>

      <CustomerFormModal :open="editing" :customer="customer.data.value" @close="editing = false" @saved="editing = false" />
      <DeviceFormModal :open="deviceModal.open" :customer-id="id" :device="deviceModal.device" @close="deviceModal.open = false" @saved="deviceModal.open = false" />
    </template>
  </div>
</template>
