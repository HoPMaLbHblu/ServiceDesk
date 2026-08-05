<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'
import { computed, ref } from 'vue'

import { ApiError, api } from '@/api/client'
import { useInvalidateWorkspace, useStaffOptions, useWorkspaceQueryKey } from '@/api/queries'
import type { Appointment } from '@/api/types'
import BookAppointmentModal from '@/components/appointments/BookAppointmentModal.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppModal from '@/components/ui/AppModal.vue'
import ErrorState from '@/components/ui/ErrorState.vue'
import FormAlert from '@/components/ui/FormAlert.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import { addDays, dayRange, localDay, startOfWeek, todayIn } from '@/lib/dates'
import { date, dateTime, time } from '@/lib/format'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()
const invalidate = useInvalidateWorkspace()
const staff = useStaffOptions()
const tz = computed(() => session.workspace?.timezone ?? 'UTC')
const today = computed(() => todayIn(tz.value))
const weekStart = ref(startOfWeek(todayIn(tz.value)))
const technician = ref('')

const days = computed(() => Array.from({ length: 7 }, (_, i) => addDays(weekStart.value, i)))
const range = computed(() => dayRange(weekStart.value, 7, tz.value))

const appointments = useQuery({
  queryKey: useWorkspaceQueryKey('appointments', 'week', range, technician),
  queryFn: () => api.get<Appointment[]>('/appointments/', { ...range.value, technician: technician.value }),
})

const byDay = computed(() => {
  const map: Record<string, Appointment[]> = Object.fromEntries(days.value.map((d) => [d, []]))
  for (const a of appointments.data.value ?? []) map[localDay(a.starts_at, tz.value)]?.push(a)
  return map
})

const weekday = (day: string) => new Intl.DateTimeFormat(undefined, { weekday: 'short', timeZone: 'UTC' }).format(new Date(`${day}T12:00:00Z`))
const dayNum = (day: string) => Number(day.slice(8))

const booking = ref<{ open: boolean; day: string | null }>({ open: false, day: null })
const selected = ref<Appointment | null>(null)
const rescheduling = ref<Appointment | null>(null)
const cancelReason = ref('')
const actionError = ref<string | null>(null)
const busy = ref<string | null>(null)

async function setStatus(status: 'completed' | 'cancelled' | 'no_show') {
  if (!selected.value) return
  busy.value = status
  actionError.value = null
  try {
    await api.post(`/appointments/${selected.value.id}/set_status/`, { status, reason: status === 'cancelled' ? cancelReason.value : '' })
    selected.value = null
    cancelReason.value = ''
    await invalidate()
  } catch (e) {
    actionError.value = e instanceof ApiError ? e.message : 'Could not update the appointment.'
  } finally {
    busy.value = null
  }
}

const tone: Record<string, string> = {
  scheduled: 'border-l-brand-600 bg-brand-50',
  completed: 'border-l-green-600 bg-green-50',
  cancelled: 'border-l-slate-400 bg-slate-100 line-through text-slate-500',
  no_show: 'border-l-red-600 bg-red-50',
}
</script>

<template>
  <div>
    <PageHeader title="Appointments" :subtitle="`Times shown in ${tz}.`">
      <template v-if="session.isManager" #actions>
        <AppButton @click="booking = { open: true, day: null }">Book appointment</AppButton>
      </template>
    </PageHeader>

    <div class="mb-4 flex flex-wrap items-center gap-2">
      <div class="flex items-center gap-1">
        <AppButton size="sm" variant="secondary" aria-label="Previous week" @click="weekStart = addDays(weekStart, -7)">‹</AppButton>
        <AppButton size="sm" variant="secondary" @click="weekStart = startOfWeek(today)">This week</AppButton>
        <AppButton size="sm" variant="secondary" aria-label="Next week" @click="weekStart = addDays(weekStart, 7)">›</AppButton>
      </div>
      <span class="text-sm font-medium">{{ date(days[0]) }} – {{ date(days[6]) }}</span>
      <select v-if="session.isManager" v-model="technician" class="field-input ml-auto w-auto" aria-label="Technician">
        <option value="">All technicians</option>
        <option v-for="s in staff.data.value ?? []" :key="s.user_id" :value="s.user_id">{{ s.full_name }}</option>
      </select>
    </div>

    <ErrorState v-if="appointments.isError.value" :error="appointments.error.value" :retry="appointments.refetch" />
    <div v-else class="grid grid-cols-1 gap-2 md:grid-cols-7" :aria-busy="appointments.isFetching.value">
      <section v-for="day in days" :key="day" class="card flex min-h-24 flex-col md:min-h-80" :aria-label="date(day)">
        <header :class="['flex items-center justify-between border-b border-slate-200 px-2 py-1.5 text-sm', day === today ? 'bg-brand-50 font-semibold text-brand-800' : '']">
          <span>{{ weekday(day) }} {{ dayNum(day) }}</span>
          <button v-if="session.isManager" type="button" class="rounded px-1 text-slate-500 hover:bg-slate-100" :aria-label="`Book on ${date(day)}`" @click="booking = { open: true, day }">+</button>
        </header>
        <ul class="flex-1 space-y-1.5 p-1.5">
          <li v-for="a in byDay[day]" :key="a.id">
            <button type="button" :class="['w-full rounded border-l-4 px-2 py-1 text-left text-xs', tone[a.status ?? 'scheduled']]" @click="selected = a">
              <span class="font-semibold tabular-nums">{{ time(a.starts_at, tz) }}</span>
              <span class="block truncate">{{ a.customer_name }}</span>
              <span class="block truncate text-slate-600">{{ a.kind_label }} · {{ a.technician_name }}</span>
            </button>
          </li>
          <li v-if="!byDay[day]?.length" class="px-1 py-2 text-xs text-slate-400 md:hidden">No appointments</li>
        </ul>
      </section>
    </div>

    <AppModal :open="!!selected" title="Appointment" @close="selected = null">
      <template v-if="selected">
        <dl class="space-y-1 text-sm">
          <div><dt class="inline font-medium">When: </dt><dd class="inline">{{ dateTime(selected.starts_at, tz) }} – {{ time(selected.ends_at, tz) }}</dd></div>
          <div><dt class="inline font-medium">Customer: </dt><dd class="inline">{{ selected.customer_name }}</dd></div>
          <div><dt class="inline font-medium">Technician: </dt><dd class="inline">{{ selected.technician_name }}</dd></div>
          <div><dt class="inline font-medium">Type: </dt><dd class="inline">{{ selected.kind_label }}</dd></div>
          <div v-if="selected.order">
            <dt class="inline font-medium">Order: </dt>
            <dd class="inline"><RouterLink :to="{ name: 'order', params: { id: selected.order } }" class="text-brand-700 hover:underline">{{ selected.order_reference }}</RouterLink></dd>
          </div>
          <div v-if="selected.notes"><dt class="inline font-medium">Notes: </dt><dd class="inline">{{ selected.notes }}</dd></div>
          <div class="pt-1"><StatusBadge :status="selected.status ?? 'scheduled'" /></div>
        </dl>
        <div v-if="selected.status === 'scheduled' && session.isManager" class="mt-4 space-y-3 border-t border-slate-200 pt-4">
          <FormAlert :message="actionError" />
          <div class="flex flex-wrap gap-2">
            <AppButton size="sm" variant="secondary" @click="rescheduling = selected; selected = null">Reschedule</AppButton>
            <AppButton size="sm" :loading="busy === 'completed'" @click="setStatus('completed')">Mark completed</AppButton>
            <AppButton size="sm" variant="secondary" :loading="busy === 'no_show'" @click="setStatus('no_show')">No-show</AppButton>
          </div>
          <div class="flex gap-2">
            <input v-model="cancelReason" class="field-input" placeholder="Reason for cancelling" aria-label="Reason for cancelling" />
            <AppButton size="sm" variant="danger" :disabled="!cancelReason.trim()" :loading="busy === 'cancelled'" @click="setStatus('cancelled')">Cancel</AppButton>
          </div>
        </div>
      </template>
    </AppModal>

    <BookAppointmentModal :open="booking.open" :day="booking.day" :technician-id="technician || null" @close="booking.open = false" @saved="booking.open = false" />
    <BookAppointmentModal :open="!!rescheduling" :appointment="rescheduling" :day="rescheduling ? localDay(rescheduling.starts_at, tz) : null" @close="rescheduling = null" @saved="rescheduling = null" />
  </div>
</template>
