<script setup lang="ts">
import { keepPreviousData, useQuery } from '@tanstack/vue-query'
import { computed, ref } from 'vue'

import { ApiError, api, download } from '@/api/client'
import { useWorkspaceQueryKey } from '@/api/queries'
import type { DashboardReport } from '@/api/types'
import AppButton from '@/components/ui/AppButton.vue'
import ErrorState from '@/components/ui/ErrorState.vue'
import LoadingState from '@/components/ui/LoadingState.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import { addDays, todayIn } from '@/lib/dates'
import { date, money } from '@/lib/format'
import { useSessionStore } from '@/stores/session'
import { useToastStore } from '@/stores/toasts'

const session = useSessionStore()
const toasts = useToastStore()
const tz = session.workspace?.timezone ?? 'UTC'
const end = ref(todayIn(tz))
const start = ref(addDays(end.value, -29))
const period = computed(() => ({ start: start.value, end: end.value }))

const report = useQuery({
  queryKey: useWorkspaceQueryKey('reports', period),
  queryFn: () => api.get<DashboardReport>('/reports/dashboard/', period.value),
  placeholderData: keepPreviousData,
})
const r = computed(() => report.data.value)
const maxDay = computed(() => Math.max(1, ...(r.value?.collected.series ?? []).map((d) => Math.abs(Number(d.amount)))))
const maxStatus = computed(() => Math.max(1, ...(r.value?.orders_by_status ?? []).map((s) => s.count)))

function preset(days: number) {
  end.value = todayIn(tz)
  start.value = addDays(end.value, -(days - 1))
}

const exporting = ref<string | null>(null)
async function exportCsv(dataset: string) {
  exporting.value = dataset
  try {
    await download(`/reports/export/${dataset}.csv`, `${dataset}.csv`, period.value)
  } catch (e) {
    toasts.error(e instanceof ApiError ? e.message : 'Export failed.')
  } finally {
    exporting.value = null
  }
}
</script>

<template>
  <div>
    <PageHeader title="Reports" :subtitle="`Dates are in ${tz}. Hover a heading's ⓘ for exactly what it counts.`" />

    <div class="mb-5 flex flex-wrap items-end gap-3">
      <div>
        <label for="report-start" class="field-label">From</label>
        <input id="report-start" v-model="start" type="date" class="field-input" />
      </div>
      <div>
        <label for="report-end" class="field-label">To</label>
        <input id="report-end" v-model="end" type="date" class="field-input" />
      </div>
      <div class="flex gap-1">
        <AppButton size="sm" variant="secondary" @click="preset(7)">7 days</AppButton>
        <AppButton size="sm" variant="secondary" @click="preset(30)">30 days</AppButton>
        <AppButton size="sm" variant="secondary" @click="preset(90)">90 days</AppButton>
      </div>
    </div>

    <LoadingState v-if="report.isPending.value" />
    <ErrorState v-else-if="report.isError.value" :error="report.error.value" :retry="report.refetch" />
    <div v-else-if="r" class="space-y-6" :class="{ 'opacity-60': report.isFetching.value }">
      <div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <div class="card p-4">
          <p class="text-xs text-slate-500" :title="r.definitions.collected">Collected (net) ⓘ</p>
          <p class="mt-1 text-2xl font-semibold" data-testid="collected-net">{{ money(r.collected.net, r.currency) }}</p>
          <p class="text-xs text-slate-500">{{ money(r.collected.gross, r.currency) }} in, {{ money(r.collected.refunds, r.currency) }} refunded</p>
        </div>
        <div class="card p-4">
          <p class="text-xs text-slate-500" :title="r.definitions.outstanding">Outstanding now ⓘ</p>
          <p class="mt-1 text-2xl font-semibold">{{ money(r.outstanding.balance, r.currency) }}</p>
          <p class="text-xs text-slate-500">{{ r.outstanding.count }} invoices · {{ money(r.outstanding.overdue_balance, r.currency) }} overdue</p>
        </div>
        <div class="card p-4">
          <p class="text-xs text-slate-500" :title="r.definitions.turnaround">Turnaround ⓘ</p>
          <p class="mt-1 text-2xl font-semibold">{{ r.turnaround.median_hours === null ? '—' : `${r.turnaround.median_hours} h` }}</p>
          <p class="text-xs text-slate-500">median of {{ r.turnaround.count }} completed · avg {{ r.turnaround.average_hours ?? '—' }} h</p>
        </div>
        <div class="card p-4">
          <p class="text-xs text-slate-500" :title="r.definitions.low_stock">Low-stock parts ⓘ</p>
          <p class="mt-1 text-2xl font-semibold">{{ r.low_stock.length }}</p>
          <RouterLink :to="{ name: 'inventory', query: { low_stock: 'true' } }" class="text-xs text-brand-700 hover:underline">View parts</RouterLink>
        </div>
      </div>

      <div class="grid gap-6 lg:grid-cols-2">
        <section class="card p-4">
          <h2 class="mb-3 font-semibold" :title="r.definitions.collected">Money collected per day</h2>
          <div class="flex h-40 items-end gap-px" role="img" :aria-label="`Daily collected amounts from ${date(r.period.start)} to ${date(r.period.end)}`">
            <div
              v-for="d in r.collected.series"
              :key="d.date"
              :title="`${date(d.date)}: ${money(d.amount, r.currency)}`"
              :class="['flex-1 rounded-t', Number(d.amount) < 0 ? 'bg-red-400' : 'bg-brand-600']"
              :style="{ height: `${Math.max(Number(d.amount) === 0 ? 0 : 2, (Math.abs(Number(d.amount)) / maxDay) * 100)}%` }"
            />
          </div>
          <div class="mt-1 flex justify-between text-xs text-slate-500"><span>{{ date(r.period.start) }}</span><span>{{ date(r.period.end) }}</span></div>
        </section>

        <section class="card p-4">
          <h2 class="mb-3 font-semibold" :title="r.definitions.orders_by_status">Orders created in the period, by current status</h2>
          <ul class="space-y-1.5 text-sm">
            <li v-for="s in r.orders_by_status" :key="s.status" class="flex items-center gap-2">
              <span class="w-36 shrink-0">{{ s.label }}</span>
              <span class="h-3 rounded bg-brand-600" :style="{ width: `${(s.count / maxStatus) * 60}%` }" aria-hidden="true" />
              <span class="tabular-nums">{{ s.count }}</span>
            </li>
          </ul>
        </section>

        <section class="card overflow-hidden">
          <h2 class="px-4 pt-4 pb-2 font-semibold" :title="r.definitions.technician_workload">Technician workload</h2>
          <div class="overflow-x-auto">
            <table class="table-base">
              <thead><tr><th scope="col">Name</th><th scope="col" class="text-right">Open</th><th scope="col" class="text-right">Completed</th><th scope="col" class="text-right">Booked next 7 days</th></tr></thead>
              <tbody class="divide-y divide-slate-100">
                <tr v-for="t in r.technician_workload" :key="t.user_id">
                  <td>{{ t.name }}</td>
                  <td class="text-right tabular-nums">{{ t.open_orders }}</td>
                  <td class="text-right tabular-nums">{{ t.completed_in_period }}</td>
                  <td class="text-right tabular-nums">{{ t.booked_hours_next_7_days }} h</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section class="card overflow-hidden">
          <h2 class="px-4 pt-4 pb-2 font-semibold" :title="r.definitions.top_parts">Most used parts</h2>
          <p v-if="!r.top_parts.length" class="px-4 pb-4 text-sm text-slate-500">No parts used in this period.</p>
          <div v-else class="overflow-x-auto">
            <table class="table-base">
              <thead><tr><th scope="col">Part</th><th scope="col" class="text-right">Used</th><th scope="col" class="text-right">Orders</th></tr></thead>
              <tbody class="divide-y divide-slate-100">
                <tr v-for="p in r.top_parts" :key="p.part_id">
                  <td>{{ p.name }} <span class="text-xs text-slate-500">{{ p.sku }}</span></td>
                  <td class="text-right tabular-nums">{{ p.quantity_used }}</td>
                  <td class="text-right tabular-nums">{{ p.orders }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <section class="card p-4">
        <h2 class="font-semibold">Export CSV</h2>
        <p class="mt-1 text-sm text-slate-600">Records in the selected period, for spreadsheets or your accountant.</p>
        <div class="mt-3 flex flex-wrap gap-2">
          <AppButton v-for="d in ['orders', 'invoices', 'payments', 'parts', 'customers']" :key="d" size="sm" variant="secondary" :loading="exporting === d" @click="exportCsv(d)">
            {{ d[0]!.toUpperCase() + d.slice(1) }}
          </AppButton>
        </div>
      </section>
    </div>
  </div>
</template>
