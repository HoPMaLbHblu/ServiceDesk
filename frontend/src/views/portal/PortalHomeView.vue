<script setup lang="ts">
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, ref } from 'vue'

import { api } from '@/api/client'
import type { PortalAppointment, PortalCustomer, PortalDevice, PortalOrder } from '@/api/types'
import AppButton from '@/components/ui/AppButton.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import ErrorState from '@/components/ui/ErrorState.vue'
import FormAlert from '@/components/ui/FormAlert.vue'
import LoadingState from '@/components/ui/LoadingState.vue'
import SelectField from '@/components/ui/SelectField.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import TextAreaField from '@/components/ui/TextAreaField.vue'
import TextField from '@/components/ui/TextField.vue'
import { useApiForm } from '@/composables/useApiForm'
import { DEVICE_KINDS, date, dateTime } from '@/lib/format'
import { useSessionStore } from '@/stores/session'
import { useToastStore } from '@/stores/toasts'

const session = useSessionStore()
const toasts = useToastStore()
const queryClient = useQueryClient()
// Portal data is keyed by the signed-in user, not a workspace.
const key = (name: string) => computed(() => ['portal', session.user?.id, name])

const customers = useQuery({ queryKey: key('customers'), queryFn: () => api.get<PortalCustomer[]>('/portal/customers/') })
const orders = useQuery({ queryKey: key('orders'), queryFn: () => api.get<PortalOrder[]>('/portal/orders/') })
const appointments = useQuery({ queryKey: key('appointments'), queryFn: () => api.get<PortalAppointment[]>('/portal/appointments/') })

const requesting = ref(false)
const form = useApiForm({ customer: '', device: '', device_kind: 'phone', device_brand: '', device_model: '', problem_description: '' })
const selectedCustomer = computed(() => customers.data.value?.find((c) => c.id === form.values.customer))
const devices = computed(() => (selectedCustomer.value?.devices ?? []) as unknown as PortalDevice[])

function startRequest() {
  form.reset({ customer: customers.data.value?.[0]?.id ?? '', device: '', device_kind: 'phone', device_brand: '', device_model: '', problem_description: '' })
  requesting.value = true
}

async function submitRequest() {
  const order = await form.submit((v) => api.post<PortalOrder>('/portal/orders/', { ...v, device: v.device || null }))
  if (order) {
    requesting.value = false
    toasts.success(`Request ${order.reference} sent to ${order.business_name}`)
    await queryClient.invalidateQueries({ queryKey: ['portal'] })
  }
}
</script>

<template>
  <div class="space-y-6">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <h1 class="text-xl font-semibold">My repairs</h1>
      <AppButton v-if="customers.data.value?.length" @click="startRequest">Request a repair</AppButton>
    </div>

    <section v-if="requesting" class="card p-5">
      <h2 class="font-semibold">Request a repair</h2>
      <form class="mt-4 space-y-4" novalidate @submit.prevent="submitRequest">
        <FormAlert :message="form.generalError.value" />
        <SelectField
          v-if="(customers.data.value?.length ?? 0) > 1"
          v-model="form.values.customer"
          label="Shop"
          :options="(customers.data.value ?? []).map((c) => ({ value: c.id, label: `${c.business_name} (${c.full_name})` }))"
        />
        <SelectField
          v-model="form.values.device"
          label="Device"
          placeholder=""
          :options="[...devices.map((d) => ({ value: d.id, label: d.label }))]"
          :error="form.fieldError('device')"
        />
        <div v-if="!form.values.device" class="grid gap-3 sm:grid-cols-3">
          <SelectField v-model="form.values.device_kind" label="Type" :options="DEVICE_KINDS" />
          <TextField v-model="form.values.device_brand" label="Brand" :error="form.fieldError('device_brand')" />
          <TextField v-model="form.values.device_model" label="Model" :error="form.fieldError('device_model')" />
        </div>
        <TextAreaField v-model="form.values.problem_description" label="What's wrong?" required :rows="3" :error="form.fieldError('problem_description')" />
        <div class="flex justify-end gap-2">
          <AppButton variant="secondary" @click="requesting = false">Cancel</AppButton>
          <AppButton type="submit" :loading="form.submitting.value">Send request</AppButton>
        </div>
      </form>
    </section>

    <section class="card">
      <h2 class="border-b border-slate-200 px-4 py-3 font-semibold">Repairs</h2>
      <LoadingState v-if="orders.isPending.value" />
      <ErrorState v-else-if="orders.isError.value" class="m-4" :error="orders.error.value" />
      <EmptyState v-else-if="!orders.data.value?.length" title="No repairs yet" />
      <ul v-else class="divide-y divide-slate-100">
        <li v-for="o in orders.data.value" :key="o.id">
          <RouterLink :to="{ name: 'portal-order', params: { id: o.id } }" class="flex items-center justify-between gap-3 px-4 py-3 hover:bg-slate-50">
            <div class="min-w-0">
              <p class="font-medium">{{ o.device }} <span class="font-normal text-slate-500">· {{ o.reference }}</span></p>
              <p class="truncate text-sm text-slate-600">{{ o.business_name }} · {{ date(o.created_at) }}</p>
            </div>
            <StatusBadge :status="o.status" />
          </RouterLink>
        </li>
      </ul>
    </section>

    <section v-if="appointments.data.value?.length" class="card">
      <h2 class="border-b border-slate-200 px-4 py-3 font-semibold">Upcoming appointments</h2>
      <ul class="divide-y divide-slate-100 text-sm">
        <li v-for="a in appointments.data.value" :key="a.id" class="flex justify-between px-4 py-3">
          <span>{{ dateTime(a.starts_at, a.timezone) }} · {{ a.kind }} at {{ a.business_name }}</span>
          <StatusBadge :status="a.status" />
        </li>
      </ul>
    </section>
    <p class="text-sm text-slate-500">Signed in as {{ session.user?.email }}.</p>
  </div>
</template>
