<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'
import { computed } from 'vue'

import { ApiError, api } from '@/api/client'
import { useInvalidateWorkspace, useStaffOptions, useWorkspaceQueryKey } from '@/api/queries'
import type { TechnicianAvailability, TimeOff } from '@/api/types'
import AppButton from '@/components/ui/AppButton.vue'
import FormAlert from '@/components/ui/FormAlert.vue'
import SelectField from '@/components/ui/SelectField.vue'
import TextField from '@/components/ui/TextField.vue'
import { useApiForm } from '@/composables/useApiForm'
import { WEEKDAYS, dateTime, zonedToUtc } from '@/lib/format'
import { useSessionStore } from '@/stores/session'
import { useToastStore } from '@/stores/toasts'

const session = useSessionStore()
const toasts = useToastStore()
const invalidate = useInvalidateWorkspace()
const staff = useStaffOptions()
const tz = computed(() => session.workspace?.timezone ?? 'UTC')
const staffOptions = computed(() => (staff.data.value ?? []).map((s) => ({ value: s.user_id, label: s.full_name })))

const availability = useQuery({
  queryKey: useWorkspaceQueryKey('technician-availability'),
  queryFn: () => api.get<TechnicianAvailability[]>('/technician-availability/'),
})
const timeOff = useQuery({ queryKey: useWorkspaceQueryKey('time-off'), queryFn: () => api.get<TimeOff[]>('/time-off/') })

const shift = useApiForm({ technician: '', weekday: '0', start_time: '09:00', end_time: '17:00' })
async function addShift() {
  const ok = await shift.submit((v) => api.post('/technician-availability/', { ...v, weekday: Number(v.weekday) }))
  if (ok) await invalidate()
}

const off = useApiForm({ technician: '', start_date: '', start_time: '09:00', end_date: '', end_time: '18:00', reason: '' })
async function addTimeOff() {
  const ok = await off.submit((v) =>
    api.post('/time-off/', {
      technician: v.technician,
      starts_at: v.start_date ? zonedToUtc(v.start_date, v.start_time, tz.value) : '',
      ends_at: v.end_date ? zonedToUtc(v.end_date, v.end_time, tz.value) : '',
      reason: v.reason,
    }),
  )
  if (ok) {
    off.reset()
    await invalidate()
  }
}

async function remove(path: string) {
  try {
    await api.delete(path)
  } catch (e) {
    toasts.error(e instanceof ApiError ? e.message : 'Could not delete.')
  } finally {
    await invalidate()
  }
}
const weekdayOptions = WEEKDAYS.map((d, i) => ({ value: String(i), label: d }))
</script>

<template>
  <div class="grid max-w-4xl gap-6">
    <section class="card p-5">
      <h2 class="font-semibold">Technician shifts</h2>
      <p class="mt-1 text-sm text-slate-600">If a technician has no shifts, they can be booked any time the shop is open.</p>
      <ul v-if="availability.data.value?.length" class="mt-3 divide-y divide-slate-100 text-sm">
        <li v-for="a in availability.data.value" :key="a.id" class="flex items-center justify-between py-2">
          <span>{{ a.technician_name }} · {{ WEEKDAYS[a.weekday] }} {{ a.start_time.slice(0, 5) }}–{{ a.end_time.slice(0, 5) }}</span>
          <button type="button" class="text-red-700 hover:underline" @click="remove(`/technician-availability/${a.id}/`)">Remove</button>
        </li>
      </ul>
      <form class="mt-4 grid gap-3 sm:grid-cols-5 sm:items-start" novalidate @submit.prevent="addShift">
        <SelectField v-model="shift.values.technician" class="sm:col-span-2" label="Technician" placeholder="" :options="staffOptions" :error="shift.fieldError('technician')" />
        <SelectField v-model="shift.values.weekday" label="Day" :options="weekdayOptions" />
        <TextField v-model="shift.values.start_time" label="From" type="time" :error="shift.fieldError('start_time')" />
        <TextField v-model="shift.values.end_time" label="To" type="time" :error="shift.fieldError('end_time') || shift.fieldError('non_field_errors')" />
        <div class="sm:col-span-5">
          <FormAlert class="mb-2" :message="shift.generalError.value" />
          <AppButton type="submit" size="sm" :loading="shift.submitting.value">Add shift</AppButton>
        </div>
      </form>
    </section>

    <section class="card p-5">
      <h2 class="font-semibold">Time off</h2>
      <ul v-if="timeOff.data.value?.length" class="mt-3 divide-y divide-slate-100 text-sm">
        <li v-for="t in timeOff.data.value" :key="t.id" class="flex items-center justify-between py-2">
          <span>{{ t.technician_name }} · {{ dateTime(t.starts_at, tz) }} – {{ dateTime(t.ends_at, tz) }}<template v-if="t.reason"> · {{ t.reason }}</template></span>
          <button type="button" class="text-red-700 hover:underline" @click="remove(`/time-off/${t.id}/`)">Remove</button>
        </li>
      </ul>
      <form class="mt-4 grid gap-3 sm:grid-cols-4" novalidate @submit.prevent="addTimeOff">
        <SelectField v-model="off.values.technician" class="sm:col-span-2" label="Technician" placeholder="" :options="staffOptions" :error="off.fieldError('technician')" />
        <TextField v-model="off.values.reason" class="sm:col-span-2" label="Reason" />
        <TextField v-model="off.values.start_date" label="From date" type="date" :error="off.fieldError('starts_at')" />
        <TextField v-model="off.values.start_time" label="From time" type="time" />
        <TextField v-model="off.values.end_date" label="Until date" type="date" :error="off.fieldError('ends_at')" />
        <TextField v-model="off.values.end_time" label="Until time" type="time" />
        <div class="sm:col-span-4">
          <FormAlert class="mb-2" :message="off.generalError.value" />
          <AppButton type="submit" size="sm" :loading="off.submitting.value">Add time off</AppButton>
        </div>
      </form>
    </section>
  </div>
</template>
