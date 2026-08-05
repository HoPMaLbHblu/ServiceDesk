<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'
import { computed, ref } from 'vue'

import { api } from '@/api/client'
import { useWorkspaceQueryKey } from '@/api/queries'
import type { Appointment, OrderDetail } from '@/api/types'
import AppButton from '@/components/ui/AppButton.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import { dateTime } from '@/lib/format'
import { useSessionStore } from '@/stores/session'

import BookAppointmentModal from './BookAppointmentModal.vue'

const props = defineProps<{ order: OrderDetail }>()
const session = useSessionStore()
const appointments = useQuery({
  queryKey: useWorkspaceQueryKey('appointments', { order: props.order.id }),
  queryFn: () => api.get<Appointment[]>('/appointments/', { order: props.order.id }),
})
const booking = ref(false)
const open = computed(() => !['completed', 'cancelled'].includes(props.order.status ?? ''))
</script>

<template>
  <section class="card p-4">
    <div class="mb-2 flex items-center justify-between">
      <h2 class="font-semibold">Appointments</h2>
      <AppButton v-if="session.isManager && open" size="sm" variant="secondary" @click="booking = true">Book</AppButton>
    </div>
    <p v-if="!appointments.data.value?.length" class="text-sm text-slate-500">None booked.</p>
    <ul v-else class="space-y-2 text-sm">
      <li v-for="a in appointments.data.value" :key="a.id" class="flex items-center justify-between gap-2">
        <span>{{ dateTime(a.starts_at, session.workspace?.timezone) }} · {{ a.kind_label }} · {{ a.technician_name }}</span>
        <StatusBadge :status="a.status ?? 'scheduled'" />
      </li>
    </ul>
    <BookAppointmentModal
      :open="booking"
      :customer="{ id: order.customer.id, name: order.customer.name }"
      :order-id="order.id"
      :technician-id="order.assigned_technician?.id ?? null"
      @close="booking = false"
      @saved="booking = false"
    />
  </section>
</template>
