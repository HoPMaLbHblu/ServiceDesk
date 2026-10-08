<script setup lang="ts">
import type { InvoiceList } from '@/api/types'
import EmptyState from '@/components/ui/EmptyState.vue'
import ErrorState from '@/components/ui/ErrorState.vue'
import LoadingState from '@/components/ui/LoadingState.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import PaginationBar from '@/components/ui/PaginationBar.vue'
import SearchInput from '@/components/ui/SearchInput.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import { useListQuery } from '@/composables/useListQuery'
import { date, money } from '@/lib/format'

const { search, page, filters, query } = useListQuery<InvoiceList>('invoices', '/invoices/', ['outstanding', 'overdue', 'status'])
</script>

<template>
  <div>
    <PageHeader title="Invoices" subtitle="Invoices are issued from a repair order once the estimate is approved." />
    <div class="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center">
      <SearchInput v-model="search" label="Search invoices" placeholder="Number, order or customer" />
      <label class="flex items-center gap-2 text-sm">
        <input v-model="filters.outstanding" type="checkbox" true-value="true" false-value="" class="h-4 w-4" /> Unpaid only
      </label>
      <label class="flex items-center gap-2 text-sm">
        <input v-model="filters.overdue" type="checkbox" true-value="true" false-value="" class="h-4 w-4" /> Overdue only
      </label>
    </div>
    <div class="card overflow-hidden">
      <LoadingState v-if="query.isPending.value" />
      <ErrorState v-else-if="query.isError.value" class="m-4" :error="query.error.value" :retry="query.refetch" />
      <EmptyState v-else-if="!query.data.value?.results.length" title="No invoices" />
      <template v-else>
        <div class="overflow-x-auto">
          <table class="table-base">
            <thead>
              <tr>
                <th scope="col">Invoice</th>
                <th scope="col">Customer</th>
                <th scope="col" class="hidden sm:table-cell">Issued</th>
                <th scope="col" class="hidden sm:table-cell">Due</th>
                <th scope="col" class="text-right">Total</th>
                <th scope="col" class="text-right">Balance</th>
                <th scope="col">Status</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100 bg-white">
              <tr v-for="i in query.data.value.results" :key="i.id" class="hover:bg-slate-50">
                <td>
                  <RouterLink :to="{ name: 'invoice', params: { id: i.id } }" class="font-medium text-brand-700 hover:underline">{{ i.reference }}</RouterLink>
                  <p class="text-xs text-slate-500">{{ i.order_reference }}</p>
                </td>
                <td>{{ i.customer_name }}</td>
                <td class="hidden whitespace-nowrap sm:table-cell">{{ date(i.issued_at) }}</td>
                <td class="hidden whitespace-nowrap sm:table-cell">
                  {{ date(i.due_date) }}
                  <span v-if="i.is_overdue" class="ml-1 text-xs font-medium text-red-700">Overdue</span>
                </td>
                <td class="text-right tabular-nums">{{ money(i.total, i.currency) }}</td>
                <td class="text-right tabular-nums">{{ money(i.balance_due, i.currency) }}</td>
                <td><StatusBadge :status="i.status === 'void' ? 'void' : i.payment_status" kind="payment" /></td>
              </tr>
            </tbody>
          </table>
        </div>
        <PaginationBar v-model:page="page" :total-pages="query.data.value.total_pages" :count="query.data.value.count" />
      </template>
    </div>
  </div>
</template>
