<script setup lang="ts">
import type { AuditLog } from '@/api/types'
import EmptyState from '@/components/ui/EmptyState.vue'
import ErrorState from '@/components/ui/ErrorState.vue'
import LoadingState from '@/components/ui/LoadingState.vue'
import PaginationBar from '@/components/ui/PaginationBar.vue'
import SearchInput from '@/components/ui/SearchInput.vue'
import { useListQuery } from '@/composables/useListQuery'
import { dateTime } from '@/lib/format'

const { search, page, query } = useListQuery<AuditLog>('audit-log', '/audit-log/')

function changes(value: unknown): string {
  if (!value || typeof value !== 'object' || !Object.keys(value).length) return ''
  return Object.entries(value as Record<string, unknown>)
    .map(([k, v]) => (Array.isArray(v) && v.length === 2 ? `${k}: ${String(v[0])} → ${String(v[1])}` : `${k}: ${typeof v === 'object' ? JSON.stringify(v) : String(v)}`))
    .join('; ')
}
</script>

<template>
  <div>
    <p class="mb-4 max-w-2xl text-sm text-slate-600">A permanent record of sensitive changes: roles, settings, prices, stock, payments, refunds and billing. Entries cannot be edited or deleted.</p>
    <div class="mb-3"><SearchInput v-model="search" label="Search audit log" placeholder="Person, record or action" /></div>
    <div class="card overflow-hidden">
      <LoadingState v-if="query.isPending.value" />
      <ErrorState v-else-if="query.isError.value" class="m-4" :error="query.error.value" />
      <EmptyState v-else-if="!query.data.value?.results.length" title="Nothing recorded" />
      <template v-else>
        <div class="overflow-x-auto">
          <table class="table-base">
            <thead><tr><th scope="col">When</th><th scope="col">Who</th><th scope="col">What</th><th scope="col">Details</th></tr></thead>
            <tbody class="divide-y divide-slate-100">
              <tr v-for="e in query.data.value.results" :key="e.id">
                <td class="whitespace-nowrap">{{ dateTime(e.created_at) }}</td>
                <td>{{ e.actor_label || 'System' }}</td>
                <td><span class="font-mono text-xs">{{ e.action }}</span><p class="text-xs text-slate-500">{{ e.entity_label }}</p></td>
                <td class="max-w-md text-xs break-words text-slate-600">{{ changes(e.changes) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <PaginationBar v-model:page="page" :total-pages="query.data.value.total_pages" :count="query.data.value.count" />
      </template>
    </div>
  </div>
</template>
