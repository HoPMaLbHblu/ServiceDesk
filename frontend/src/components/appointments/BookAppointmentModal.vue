<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'
import { computed, ref, watch } from 'vue'

import { ApiError, api } from '@/api/client'
import { useInvalidateWorkspace, useStaffOptions, useWorkspaceQueryKey } from '@/api/queries'
import type { Appointment, Customer, Paginated } from '@/api/types'
import AppButton from '@/components/ui/AppButton.vue'
import AppModal from '@/components/ui/AppModal.vue'
import FormAlert from '@/components/ui/FormAlert.vue'
import SelectField from '@/components/ui/SelectField.vue'
import TextField from '@/components/ui/TextField.vue'
import { useDebounced } from '@/composables/useDebounced'
import { todayIn } from '@/lib/dates'
import { time } from '@/lib/format'
import { useSessionStore } from '@/stores/session'
import { useToastStore } from '@/stores/toasts'

const props = defineProps<{
  open: boolean
  /** Reschedule this appointment instead of booking a new one. */
  appointment?: Appointment | null
  customer?: { id: string; name: string } | null
  orderId?: string | null
  technicianId?: string | null
  day?: string | null
}>()
const emit = defineEmits<{ close: []; saved: [appointment: Appointment] }>()

const session = useSessionStore()
const toasts = useToastStore()
const invalidate = useInvalidateWorkspace()
const staff = useStaffOptions()
const tz = computed(() => session.workspace?.timezone ?? 'UTC')

const customerId = ref('')
const customerName = ref('')
const technician = ref('')
const kind = ref('diagnosis')
const day = ref('')
const duration = ref(60)
const slot = ref('')
const notes = ref('')
const error = ref<string | null>(null)
const fieldErrors = ref<Record<string, string[]>>({})
const saving = ref(false)

watch(
  () => props.open,
  (open) => {
    if (!open) return
    const a = props.appointment
    customerId.value = a?.customer ?? props.customer?.id ?? ''
    customerName.value = a?.customer_name ?? props.customer?.name ?? ''
    technician.value = a?.technician ?? props.technicianId ?? ''
    kind.value = a?.kind ?? 'diagnosis'
    day.value = props.day ?? todayIn(tz.value)
    duration.value = a ? Math.round((new Date(a.ends_at).getTime() - new Date(a.starts_at).getTime()) / 60000) : 60
    slot.value = ''
    notes.value = ''
    error.value = null
    fieldErrors.value = {}
  },
  { immediate: true },
)

const search = ref('')
const debounced = useDebounced(search, 250)
const customers = useQuery({
  queryKey: useWorkspaceQueryKey('customers', { search: debounced, picker: true }),
  queryFn: () => api.get<Paginated<Customer>>('/customers/', { search: debounced.value, page_size: 8 }),
  enabled: computed(() => props.open && !customerId.value),
})

const slots = useQuery({
  queryKey: useWorkspaceQueryKey('availability', technician, day, duration),
  queryFn: () => api.get<string[]>('/appointments/availability/', { technician: technician.value, date: day.value, duration_minutes: duration.value }),
  enabled: computed(() => props.open && !!technician.value && !!day.value),
})
watch([technician, day, duration], () => (slot.value = ''))

async function submit() {
  if (!slot.value) {
    error.value = 'Choose a free time.'
    return
  }
  saving.value = true
  error.value = null
  fieldErrors.value = {}
  try {
    const result = props.appointment
      ? await api.post<Appointment>(`/appointments/${props.appointment.id}/reschedule/`, {
          starts_at: slot.value,
          duration_minutes: duration.value,
          technician: technician.value,
        })
      : await api.post<Appointment>('/appointments/', {
          customer: customerId.value,
          technician: technician.value,
          order: props.orderId ?? null,
          kind: kind.value,
          starts_at: slot.value,
          duration_minutes: duration.value,
          notes: notes.value,
        })
    toasts.success(props.appointment ? 'Appointment moved' : 'Appointment booked. A confirmation email is on its way.')
    await invalidate()
    emit('saved', result)
  } catch (e) {
    if (e instanceof ApiError) {
      fieldErrors.value = e.fields
      error.value = e.code === 'appointment_conflict' ? 'That time was just taken. Pick another free slot.' : e.message
      if (e.isConflict) await slots.refetch()
    } else error.value = 'Could not save the appointment.'
  } finally {
    saving.value = false
  }
}

const kinds = [
  { value: 'drop_off', label: 'Drop-off' },
  { value: 'diagnosis', label: 'Diagnosis' },
  { value: 'repair', label: 'Repair' },
  { value: 'pickup', label: 'Pickup' },
]
</script>

<template>
  <AppModal :open="open" :title="appointment ? 'Reschedule appointment' : 'Book appointment'" size="lg" @close="emit('close')">
    <form id="book-form" class="space-y-4" novalidate @submit.prevent="submit">
      <FormAlert :message="error" />
      <div v-if="customerId" class="flex items-center justify-between rounded-md bg-slate-50 px-3 py-2 text-sm">
        <span>Customer: <strong>{{ customerName }}</strong></span>
        <button v-if="!appointment && !customer" type="button" class="text-brand-700 hover:underline" @click="customerId = ''">Change</button>
      </div>
      <div v-else>
        <TextField v-model="search" label="Customer" placeholder="Search by name or phone" :error="fieldErrors.customer?.[0]" />
        <ul class="mt-1 max-h-40 divide-y divide-slate-100 overflow-y-auto rounded-md border border-slate-200">
          <li v-for="c in customers.data.value?.results ?? []" :key="c.id">
            <button type="button" class="w-full px-3 py-1.5 text-left text-sm hover:bg-slate-50" @click="customerId = c.id; customerName = c.full_name">
              {{ c.full_name }} <span class="text-slate-500">{{ c.phone }}</span>
            </button>
          </li>
        </ul>
      </div>
      <div class="grid gap-3 sm:grid-cols-2">
        <SelectField
          v-model="technician"
          label="Technician"
          placeholder=""
          required
          :options="(staff.data.value ?? []).map((s) => ({ value: s.user_id, label: s.full_name }))"
          :error="fieldErrors.technician?.[0]"
        />
        <SelectField v-if="!appointment" v-model="kind" label="Type" :options="kinds" />
        <TextField v-model="day" label="Date" type="date" required />
        <div>
          <label for="book-duration" class="field-label">Duration</label>
          <select id="book-duration" v-model.number="duration" class="field-input">
            <option v-for="m in [15, 30, 45, 60, 90, 120, 180]" :key="m" :value="m">{{ m }} minutes</option>
          </select>
        </div>
      </div>
      <fieldset>
        <legend class="field-label">Free times ({{ tz }})</legend>
        <p v-if="!technician" class="text-sm text-slate-500">Choose a technician to see free times.</p>
        <p v-else-if="slots.isFetching.value && !slots.data.value" class="text-sm text-slate-500">Checking availability…</p>
        <p v-else-if="slots.isError.value" class="text-sm text-red-700">{{ (slots.error.value as Error).message }}</p>
        <p v-else-if="!slots.data.value?.length" class="text-sm text-slate-500">No free time that day. Try another date or technician.</p>
        <div v-else class="grid grid-cols-3 gap-2 sm:grid-cols-6" data-testid="slots">
          <label
            v-for="s in slots.data.value"
            :key="s"
            :class="['cursor-pointer rounded-md border px-2 py-1.5 text-center text-sm', slot === s ? 'border-brand-600 bg-brand-50 font-medium text-brand-800' : 'border-slate-300 hover:bg-slate-50']"
          >
            <input v-model="slot" type="radio" name="slot" :value="s" class="sr-only" />
            {{ time(s, tz) }}
          </label>
        </div>
      </fieldset>
      <TextField v-if="!appointment" v-model="notes" label="Notes" />
    </form>
    <template #footer>
      <AppButton variant="secondary" @click="emit('close')">Cancel</AppButton>
      <AppButton type="submit" form="book-form" :loading="saving" :disabled="!customerId || !slot">{{ appointment ? 'Move appointment' : 'Book' }}</AppButton>
    </template>
  </AppModal>
</template>
