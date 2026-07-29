<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'
import { computed } from 'vue'

import { api } from '@/api/client'
import { useWorkspaceQueryKey } from '@/api/queries'
import type { Appointment, OrderList, Paginated, Part } from '@/api/types'
import EmptyState from '@/components/ui/EmptyState.vue'
import ErrorState from '@/components/ui/ErrorState.vue'
import LoadingState from '@/components/ui/LoadingState.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import { dayRange, todayIn } from '@/lib/dates'
import { STATUS_LABELS, date, time } from '@/lib/format'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()
const tz = computed(() => session.workspace?.timezone ?? 'UTC')
const today = computed(() => todayIn(tz.value))

const appointments = useQuery({
  queryKey: useWorkspaceQueryKey('appointments', 'today', today),
  queryFn: () => api.get<Appointment[]>('/appointments/', dayRange(today.value, 1, tz.value)),
})

const openOrders = useQuery({
  queryKey: useWorkspaceQueryKey('orders', { open: true, page_size: 100, ordering: 'expected_completion_date' }),
  queryFn: () => api.get<Paginated<OrderList>>('/orders/', { open: true, page_size: 100, ordering: 'expected_completion_date' }),
})

const lowStock = useQuery({
  queryKey: useWorkspaceQueryKey('parts', { low_stock: true }),
  queryFn: () => api.get<Paginated<Part>>('/parts/', { low_stock: true, is_active: true, page_size: 10 }),
})

const byStatus = computed(() => {
  const counts: Record<string, number> = {}
  for (const order of openOrders.data.value?.results ?? []) counts[order.status ?? 'new'] = (counts[order.status ?? 'new'] ?? 0) + 1
  return Object.keys(STATUS_LABELS)
    .filter((s) => s !== 'completed' && s !== 'cancelled')
    .map((status) => ({ status, count: counts[status] ?? 0 }))
})

const needsAttention = computed(() =>
  (openOrders.data.value?.results ?? []).filter(
    (o) => o.status === 'ready_for_pickup' || o.status === 'awaiting_approval' || (o.expected_completion_date && o.expected_completion_date < today.value),
  ),
)
const scheduled = computed(() => (appointments.data.value ?? []).filter((a) => a.status !== 'cancelled'))
</script>

<template>
  <div>
    <PageHeader :title="`Good to see you, ${session.user?.full_name.split(' ')[0] ?? ''}`" :subtitle="`${session.workspace?.name} · ${date(today)}`">
      <template v-if="session.isManager" #actions>
        <RouterLink :to="{ name: 'order-new' }" class="rounded-md bg-brand-600 px-3.5 py-2 text-sm font-medium text-white hover:bg-brand-700">New repair order</RouterLink>
      </template>
    </PageHeader>

    <section aria-labelledby="pipeline" class="mb-6">
      <h2 id="pipeline" class="sr-only">Open orders by status</h2>
      <div class="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <RouterLink
          v-for="item in byStatus"
          :key="item.status"
          :to="{ name: 'orders', query: { status: item.status } }"
          class="card p-3 hover:border-brand-600"
        >
          <p class="text-xs text-slate-500">{{ STATUS_LABELS[item.status] }}</p>
          <p class="mt-1 text-2xl font-semibold">{{ openOrders.isPending.value ? '…' : item.count }}</p>
        </RouterLink>
      </div>
    </section>

    <div class="grid gap-6 lg:grid-cols-2">
      <section class="card" aria-labelledby="today-appointments">
        <h2 id="today-appointments" class="border-b border-slate-200 px-4 py-3 font-semibold">Today's appointments</h2>
        <LoadingState v-if="appointments.isPending.value" />
        <ErrorState v-else-if="appointments.isError.value" class="m-4" :error="appointments.error.value" :retry="appointments.refetch" />
        <EmptyState v-else-if="!scheduled.length" title="No appointments today" />
        <ul v-else class="divide-y divide-slate-100">
          <li v-for="a in scheduled" :key="a.id" class="flex items-start gap-3 px-4 py-3 text-sm">
            <span class="w-24 shrink-0 font-medium tabular-nums">{{ time(a.starts_at, tz) }}–{{ time(a.ends_at, tz) }}</span>
            <div class="min-w-0 flex-1">
              <p class="font-medium">{{ a.customer_name }} <span class="font-normal text-slate-500">· {{ a.kind_label }}</span></p>
              <p class="text-slate-600">
                {{ a.technician_name }}
                <template v-if="a.order"> · <RouterLink :to="{ name: 'order', params: { id: a.order } }" class="text-brand-700 hover:underline">{{ a.order_reference }}</RouterLink></template>
              </p>
            </div>
            <StatusBadge :status="a.status ?? 'scheduled'" />
          </li>
        </ul>
      </section>

      <section class="card" aria-labelledby="attention">
        <h2 id="attention" class="border-b border-slate-200 px-4 py-3 font-semibold">Needs attention</h2>
        <LoadingState v-if="openOrders.isPending.value" />
        <ErrorState v-else-if="openOrders.isError.value" class="m-4" :error="openOrders.error.value" :retry="openOrders.refetch" />
        <EmptyState v-else-if="!needsAttention.length" title="Nothing waiting" description="Overdue, ready-for-pickup and awaiting-approval orders show up here." />
        <ul v-else class="divide-y divide-slate-100">
          <li v-for="o in needsAttention" :key="o.id">
            <RouterLink :to="{ name: 'order', params: { id: o.id } }" class="flex items-center justify-between gap-3 px-4 py-3 text-sm hover:bg-slate-50">
              <div class="min-w-0">
                <p class="font-medium">{{ o.reference }} · {{ o.customer.name }}</p>
                <p class="truncate text-slate-600">{{ o.device_label }}<template v-if="o.expected_completion_date"> · due {{ date(o.expected_completion_date) }}</template></p>
              </div>
              <StatusBadge :status="o.status ?? 'new'" />
            </RouterLink>
          </li>
        </ul>
      </section>

      <section v-if="lowStock.data.value?.results.length" class="card lg:col-span-2" aria-labelledby="low-stock">
        <h2 id="low-stock" class="border-b border-slate-200 px-4 py-3 font-semibold">Low stock</h2>
        <ul class="divide-y divide-slate-100">
          <li v-for="p in lowStock.data.value.results" :key="p.id">
            <RouterLink :to="{ name: 'part', params: { id: p.id } }" class="flex justify-between px-4 py-2.5 text-sm hover:bg-slate-50">
              <span>{{ p.name }} <span class="text-slate-500">({{ p.sku }})</span></span>
              <span class="tabular-nums text-amber-800">{{ p.quantity_available }} available · min {{ p.low_stock_threshold }}</span>
            </RouterLink>
          </li>
        </ul>
      </section>
    </div>
  </div>
</template>
