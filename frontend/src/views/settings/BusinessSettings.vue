<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'
import { ref, watch } from 'vue'

import { ApiError, api } from '@/api/client'
import { useBusiness, useInvalidateWorkspace, useWorkspaceQueryKey } from '@/api/queries'
import type { BusinessHours } from '@/api/types'
import AppButton from '@/components/ui/AppButton.vue'
import FormAlert from '@/components/ui/FormAlert.vue'
import SelectField from '@/components/ui/SelectField.vue'
import TextAreaField from '@/components/ui/TextAreaField.vue'
import TextField from '@/components/ui/TextField.vue'
import { useApiForm } from '@/composables/useApiForm'
import { useUnsavedChanges } from '@/composables/useUnsavedChanges'
import { WEEKDAYS } from '@/lib/format'
import { useSessionStore } from '@/stores/session'
import { useToastStore } from '@/stores/toasts'

const session = useSessionStore()
const toasts = useToastStore()
const invalidate = useInvalidateWorkspace()
const business = useBusiness()

const form = useApiForm({
  name: '',
  timezone: '',
  currency: 'USD',
  tax_rate: '0',
  default_labor_rate: '0',
  estimate_valid_days: 14,
  email: '',
  phone: '',
  address: '',
})
useUnsavedChanges(form.dirty)

watch(
  () => business.data.value,
  (b) => {
    if (!b) return
    form.reset({
      name: b.name,
      timezone: b.timezone ?? 'UTC',
      currency: b.currency ?? 'USD',
      tax_rate: b.tax_rate ?? '0',
      default_labor_rate: b.default_labor_rate ?? '0',
      estimate_valid_days: b.estimate_valid_days ?? 14,
      email: b.email ?? '',
      phone: b.phone ?? '',
      address: b.address ?? '',
    })
  },
  { immediate: true },
)

const zones = ((Intl as unknown as { supportedValuesOf?: (k: string) => string[] }).supportedValuesOf?.('timeZone') ?? ['UTC']).map((z) => ({ value: z, label: z }))
const currencies = ['USD', 'EUR', 'GBP', 'CAD', 'AUD', 'UAH', 'PLN'].map((c) => ({ value: c, label: c }))

async function save() {
  const ok = await form.submit((v) => api.patch('/business/', v))
  if (ok) {
    // Name, timezone and currency are part of the session.
    await session.restore()
    await invalidate()
    toasts.success('Business settings saved')
  }
}

const hours = useQuery({
  queryKey: useWorkspaceQueryKey('business-hours'),
  queryFn: () => api.get<BusinessHours[]>('/business/hours/'),
})
const hoursDraft = ref<BusinessHours[]>([])
watch(
  () => hours.data.value,
  (h) => {
    hoursDraft.value = Array.from({ length: 7 }, (_, weekday) => {
      const row = h?.find((r) => r.weekday === weekday)
      return { weekday, opens_at: row?.opens_at?.slice(0, 5) ?? '09:00', closes_at: row?.closes_at?.slice(0, 5) ?? '18:00', is_closed: row?.is_closed ?? false }
    })
  },
  { immediate: true },
)
const hoursError = ref<string | null>(null)
const savingHours = ref(false)
async function saveHours() {
  savingHours.value = true
  hoursError.value = null
  try {
    await api.put('/business/hours/', hoursDraft.value.map((h) => (h.is_closed ? { ...h, opens_at: null, closes_at: null } : h)))
    await invalidate()
    toasts.success('Opening hours saved')
  } catch (e) {
    hoursError.value = e instanceof ApiError ? (Object.values(e.fields)[0]?.[0] ?? e.message) : 'Could not save hours.'
  } finally {
    savingHours.value = false
  }
}
</script>

<template>
  <div class="grid max-w-3xl gap-6">
    <section class="card p-5">
      <h2 class="font-semibold">Business details</h2>
      <form class="mt-4 space-y-4" novalidate @submit.prevent="save">
        <FormAlert :message="form.generalError.value" />
        <TextField v-model="form.values.name" label="Business name" required :error="form.fieldError('name')" />
        <div class="grid gap-3 sm:grid-cols-2">
          <SelectField v-model="form.values.timezone" label="Timezone" :options="zones" :error="form.fieldError('timezone')" />
          <SelectField v-model="form.values.currency" label="Currency" :options="currencies" :error="form.fieldError('currency')" />
          <TextField v-model="form.values.tax_rate" label="Tax rate (%)" inputmode="decimal" :error="form.fieldError('tax_rate')" hint="Applies to new estimates. Sent estimates and issued invoices keep their rate." />
          <TextField v-model="form.values.default_labor_rate" label="Default labour rate per hour" inputmode="decimal" :error="form.fieldError('default_labor_rate')" />
          <TextField v-model.number="form.values.estimate_valid_days" label="Estimates valid for (days)" type="number" :error="form.fieldError('estimate_valid_days')" />
          <TextField v-model="form.values.phone" label="Phone" type="tel" :error="form.fieldError('phone')" />
          <TextField v-model="form.values.email" label="Email shown to customers" type="email" :error="form.fieldError('email')" />
        </div>
        <TextAreaField v-model="form.values.address" label="Address (printed on invoices)" :rows="2" :error="form.fieldError('address')" />
        <AppButton type="submit" :loading="form.submitting.value" :disabled="!form.dirty.value">Save changes</AppButton>
      </form>
    </section>

    <section class="card p-5">
      <h2 class="font-semibold">Opening hours</h2>
      <p class="mt-1 text-sm text-slate-600">Appointments can only be booked inside these hours ({{ session.workspace?.timezone }}).</p>
      <FormAlert class="mt-3" :message="hoursError" />
      <ul class="mt-4 space-y-2">
        <li v-for="h in hoursDraft" :key="h.weekday" class="flex flex-wrap items-center gap-2 text-sm">
          <span class="w-24">{{ WEEKDAYS[h.weekday] }}</span>
          <label class="flex items-center gap-1"><input v-model="h.is_closed" type="checkbox" /> Closed</label>
          <template v-if="!h.is_closed">
            <input v-model="h.opens_at" type="time" class="field-input w-auto" :aria-label="`${WEEKDAYS[h.weekday]} opens`" />
            <span>–</span>
            <input v-model="h.closes_at" type="time" class="field-input w-auto" :aria-label="`${WEEKDAYS[h.weekday]} closes`" />
          </template>
        </li>
      </ul>
      <AppButton class="mt-4" :loading="savingHours" @click="saveHours">Save hours</AppButton>
    </section>
  </div>
</template>
