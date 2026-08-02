<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api } from '@/api/client'
import { useInvalidateWorkspace, useStaffOptions, useWorkspaceQueryKey } from '@/api/queries'
import type { Customer, Device, OrderDetail, Paginated } from '@/api/types'
import CustomerFormModal from '@/components/customers/CustomerFormModal.vue'
import DeviceFormModal from '@/components/customers/DeviceFormModal.vue'
import AppButton from '@/components/ui/AppButton.vue'
import FormAlert from '@/components/ui/FormAlert.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import SelectField from '@/components/ui/SelectField.vue'
import TextAreaField from '@/components/ui/TextAreaField.vue'
import TextField from '@/components/ui/TextField.vue'
import { useApiForm } from '@/composables/useApiForm'
import { useDebounced } from '@/composables/useDebounced'
import { useUnsavedChanges } from '@/composables/useUnsavedChanges'
import { PRIORITIES } from '@/lib/format'

const route = useRoute()
const router = useRouter()
const invalidate = useInvalidateWorkspace()
const staff = useStaffOptions()

const form = useApiForm({
  customer: typeof route.query.customer === 'string' ? route.query.customer : '',
  device: '',
  problem_description: '',
  priority: 'normal',
  assigned_technician: '',
  expected_completion_date: '',
})
useUnsavedChanges(form.dirty)

const customerSearch = ref('')
const debouncedSearch = useDebounced(customerSearch, 250)
const customers = useQuery({
  queryKey: useWorkspaceQueryKey('customers', { search: debouncedSearch, picker: true }),
  queryFn: () => api.get<Paginated<Customer>>('/customers/', { search: debouncedSearch.value, page_size: 10, is_archived: false }),
})
const selectedCustomer = useQuery({
  queryKey: useWorkspaceQueryKey('customer', computed(() => form.values.customer)),
  queryFn: () => api.get<Customer>(`/customers/${form.values.customer}/`),
  enabled: computed(() => !!form.values.customer),
})
const devices = useQuery({
  queryKey: useWorkspaceQueryKey('customer', computed(() => form.values.customer), 'devices'),
  queryFn: () => api.get<Device[]>(`/customers/${form.values.customer}/devices/`),
  enabled: computed(() => !!form.values.customer),
})
watch(
  () => devices.data.value,
  (list) => {
    if (list?.length === 1 && !form.values.device) form.values.device = list[0]!.id
  },
)

const newCustomer = ref(false)
const newDevice = ref(false)
const technicians = computed(() => (staff.data.value ?? []).map((s) => ({ value: s.user_id, label: `${s.full_name} (${s.role})` })))

function pickCustomer(c: Customer) {
  form.values.customer = c.id
  form.values.device = ''
}

async function onSubmit() {
  const order = await form.submit((v) =>
    api.post<OrderDetail>('/orders/', {
      ...v,
      assigned_technician: v.assigned_technician || null,
      expected_completion_date: v.expected_completion_date || null,
    }),
  )
  if (order) {
    await invalidate()
    await router.push({ name: 'order', params: { id: order.id } })
  }
}
</script>

<template>
  <div class="mx-auto max-w-3xl">
    <PageHeader title="New repair order">
      <template #breadcrumb><RouterLink :to="{ name: 'orders' }" class="text-sm text-slate-500 hover:underline">← Repair orders</RouterLink></template>
    </PageHeader>
    <form class="space-y-6" novalidate @submit.prevent="onSubmit">
      <FormAlert :message="form.generalError.value" />

      <section class="card p-4">
        <h2 class="mb-3 font-semibold">Customer</h2>
        <div v-if="form.values.customer && selectedCustomer.data.value" class="flex items-center justify-between rounded-md bg-slate-50 px-3 py-2">
          <div>
            <p class="font-medium">{{ selectedCustomer.data.value.full_name }}</p>
            <p class="text-sm text-slate-600">{{ selectedCustomer.data.value.phone || selectedCustomer.data.value.email }}</p>
          </div>
          <button type="button" class="text-sm text-brand-700 hover:underline" @click="form.values.customer = ''">Change</button>
        </div>
        <template v-else>
          <TextField v-model="customerSearch" label="Find customer" placeholder="Name, phone or email" :error="form.fieldError('customer')" />
          <ul class="mt-2 max-h-60 divide-y divide-slate-100 overflow-y-auto rounded-md border border-slate-200" role="listbox" aria-label="Matching customers">
            <li v-for="c in customers.data.value?.results ?? []" :key="c.id">
              <button type="button" class="w-full px-3 py-2 text-left text-sm hover:bg-slate-50" @click="pickCustomer(c)">
                <span class="font-medium">{{ c.full_name }}</span> <span class="text-slate-500">{{ c.phone || c.email }}</span>
              </button>
            </li>
            <li v-if="customers.data.value && !customers.data.value.results.length" class="px-3 py-2 text-sm text-slate-500">No matches.</li>
          </ul>
          <AppButton class="mt-3" size="sm" variant="secondary" @click="newCustomer = true">New customer</AppButton>
        </template>
      </section>

      <section v-if="form.values.customer" class="card p-4">
        <h2 class="mb-3 font-semibold">Device</h2>
        <div class="flex flex-col gap-2 sm:flex-row sm:items-end">
          <SelectField
            v-model="form.values.device"
            class="flex-1"
            label="Device"
            placeholder=""
            required
            :options="(devices.data.value ?? []).map((d) => ({ value: d.id, label: d.label }))"
            :error="form.fieldError('device')"
          />
          <AppButton variant="secondary" @click="newDevice = true">Add device</AppButton>
        </div>
      </section>

      <section class="card space-y-4 p-4">
        <h2 class="font-semibold">Repair</h2>
        <TextAreaField v-model="form.values.problem_description" label="Problem reported by the customer" required :rows="4" :error="form.fieldError('problem_description')" />
        <div class="grid gap-3 sm:grid-cols-3">
          <SelectField v-model="form.values.priority" label="Priority" :options="PRIORITIES" :error="form.fieldError('priority')" />
          <SelectField v-model="form.values.assigned_technician" label="Technician" placeholder="" :options="technicians" :error="form.fieldError('assigned_technician')" />
          <TextField v-model="form.values.expected_completion_date" label="Promised by" type="date" :error="form.fieldError('expected_completion_date')" />
        </div>
      </section>

      <div class="flex justify-end gap-2">
        <RouterLink :to="{ name: 'orders' }" class="rounded-md border border-slate-300 bg-white px-3.5 py-2 text-sm font-medium">Cancel</RouterLink>
        <AppButton type="submit" :loading="form.submitting.value">Create order</AppButton>
      </div>
    </form>

    <CustomerFormModal :open="newCustomer" @close="newCustomer = false" @saved="(c) => { newCustomer = false; pickCustomer(c) }" />
    <DeviceFormModal
      v-if="form.values.customer"
      :open="newDevice"
      :customer-id="form.values.customer"
      @close="newDevice = false"
      @saved="(d) => { newDevice = false; form.values.device = d.id }"
    />
  </div>
</template>
