<script setup lang="ts">
import type { OrderList } from '@/api/types'
import { useStaffOptions } from '@/api/queries'
import EmptyState from '@/components/ui/EmptyState.vue'
import ErrorState from '@/components/ui/ErrorState.vue'
import LoadingState from '@/components/ui/LoadingState.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import PaginationBar from '@/components/ui/PaginationBar.vue'
import SearchInput from '@/components/ui/SearchInput.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import { useListQuery } from '@/composables/useListQuery'
import { STATUS_LABELS, date, label } from '@/lib/format'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()
const staff = useStaffOptions()
const { search, page, filters, query } = useListQuery<OrderList>('orders', '/orders/', ['status', 'open', 'technician', 'priority'])
if (!filters.value.status && !filters.value.open) filters.value.open = 'true'

const views = [
  { key: 'open', label: 'Open' },
  ...Object.entries(STATUS_LABELS).map(([key, text]) => ({ key, label: text })),
  { key: 'all', label: 'All' },
]

function current() {
  if (filters.value.status) return filters.value.status
  return filters.value.open === 'true' ? 'open' : 'all'
}

function choose(key: string) {
  filters.value = {
    ...filters.value,
    status: key === 'open' || key === 'all' ? '' : key,
    open: key === 'open' ? 'true' : '',
  }
}

const priorityTone: Record<string, string> = { urgent: 'text-red-700 font-semibold', high: 'text-amber-800', low: 'text-slate-500' }
</script>

<template>
  <div>
    <PageHeader title="Repair orders" :subtitle="session.isTechnician ? 'Orders assigned to you.' : undefined">
      <template v-if="session.isManager" #actions>
        <RouterLink :to="{ name: 'order-new' }" class="rounded-md bg-brand-600 px-3.5 py-2 text-sm font-medium text-white hover:bg-brand-700">New repair order</RouterLink>
      </template>
    </PageHeader>

    <div class="mb-3 -mx-1 flex gap-1 overflow-x-auto pb-1" role="tablist" aria-label="Filter by status">
      <button
        v-for="v in views"
        :key="v.key"
        type="button"
        role="tab"
        :aria-selected="current() === v.key"
        :class="['shrink-0 rounded-full px-3 py-1 text-sm whitespace-nowrap', current() === v.key ? 'bg-slate-900 text-white' : 'bg-white text-slate-700 ring-1 ring-slate-300 hover:bg-slate-50']"
        @click="choose(v.key)"
      >
        {{ v.label }}
      </button>
    </div>

    <div class="mb-3 flex flex-col gap-2 sm:flex-row">
      <SearchInput v-model="search" label="Search orders" placeholder="RO-12, customer, phone, serial…" />
      <select v-if="session.isManager" v-model="filters.technician" class="field-input sm:max-w-48" aria-label="Technician">
        <option value="">All technicians</option>
        <option v-for="s in staff.data.value ?? []" :key="s.user_id" :value="s.user_id">{{ s.full_name }}</option>
      </select>
      <select v-model="filters.priority" class="field-input sm:max-w-40" aria-label="Priority">
        <option value="">Any priority</option>
        <option v-for="p in ['urgent', 'high', 'normal', 'low']" :key="p" :value="p">{{ label(p) }}</option>
      </select>
    </div>

    <div class="card overflow-hidden">
      <LoadingState v-if="query.isPending.value" />
      <ErrorState v-else-if="query.isError.value" class="m-4" :error="query.error.value" :retry="query.refetch" />
      <EmptyState v-else-if="!query.data.value?.results.length" title="No repair orders here" :description="search ? 'Try a different search.' : undefined" />
      <template v-else>
        <!-- Cards on small screens -->
        <ul class="divide-y divide-slate-100 md:hidden">
          <li v-for="o in query.data.value.results" :key="o.id">
            <RouterLink :to="{ name: 'order', params: { id: o.id } }" class="block px-4 py-3 hover:bg-slate-50">
              <div class="flex items-center justify-between gap-2">
                <span class="font-medium">{{ o.reference }}</span>
                <StatusBadge :status="o.status ?? 'new'" />
              </div>
              <p class="mt-1 text-sm">{{ o.customer.name }} · {{ o.device_label }}</p>
              <p class="mt-0.5 text-xs text-slate-500">
                {{ o.assigned_technician?.name ?? 'Unassigned' }}<template v-if="o.expected_completion_date"> · due {{ date(o.expected_completion_date) }}</template>
              </p>
            </RouterLink>
          </li>
        </ul>
        <div class="hidden overflow-x-auto md:block">
          <table class="table-base">
            <thead>
              <tr>
                <th scope="col">Order</th>
                <th scope="col">Customer · device</th>
                <th scope="col">Status</th>
                <th scope="col">Payment</th>
                <th scope="col">Technician</th>
                <th scope="col">Due</th>
                <th scope="col">Priority</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100 bg-white">
              <tr v-for="o in query.data.value.results" :key="o.id" class="hover:bg-slate-50">
                <td><RouterLink :to="{ name: 'order', params: { id: o.id } }" class="font-medium text-brand-700 hover:underline">{{ o.reference }}</RouterLink></td>
                <td>
                  <p>{{ o.customer.name }}</p>
                  <p class="text-xs text-slate-500">{{ o.device_label }}</p>
                </td>
                <td><StatusBadge :status="o.status ?? 'new'" /></td>
                <td><StatusBadge :status="o.payment_status ?? 'not_invoiced'" kind="payment" /></td>
                <td>{{ o.assigned_technician?.name ?? '—' }}</td>
                <td class="whitespace-nowrap">{{ date(o.expected_completion_date) }}</td>
                <td :class="priorityTone[o.priority ?? 'normal']">{{ label(o.priority ?? 'normal') }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <PaginationBar v-model:page="page" :total-pages="query.data.value.total_pages" :count="query.data.value.count" />
      </template>
    </div>
  </div>
</template>
