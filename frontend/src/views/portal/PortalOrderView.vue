<script setup lang="ts">
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, ref } from 'vue'

import { ApiError, api, download } from '@/api/client'
import type { PortalAttachment, PortalEvent, PortalInvoice, PortalOrderDetail, PublicEstimate } from '@/api/types'
import EstimateReview from '@/components/portal/EstimateReview.vue'
import AppButton from '@/components/ui/AppButton.vue'
import ErrorState from '@/components/ui/ErrorState.vue'
import LoadingState from '@/components/ui/LoadingState.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import { date, dateTime, money } from '@/lib/format'
import { useSessionStore } from '@/stores/session'
import { useToastStore } from '@/stores/toasts'

const props = defineProps<{ id: string }>()
const session = useSessionStore()
const toasts = useToastStore()
const queryClient = useQueryClient()
const order = useQuery({
  queryKey: computed(() => ['portal', session.user?.id, 'order', props.id]),
  queryFn: () => api.get<PortalOrderDetail>(`/portal/orders/${props.id}/`),
})
const o = computed(() => order.data.value)
const timeline = computed(() => (o.value?.timeline ?? []) as unknown as PortalEvent[])
const attachments = computed(() => (o.value?.attachments ?? []) as unknown as PortalAttachment[])
const invoices = computed(() => (o.value?.invoices ?? []) as unknown as PortalInvoice[])
const estimates = computed(() => [...((o.value?.estimates ?? []) as unknown as PublicEstimate[])].sort((a, b) => b.version - a.version))
const latest = computed(() => estimates.value[0] ?? null)

const busy = ref(false)
const error = ref<string | null>(null)
async function decide(payload: { decision: 'approve' | 'reject'; note: string; content_hash: string }) {
  if (!latest.value) return
  busy.value = true
  error.value = null
  try {
    await api.post(`/portal/estimates/${latest.value.id}/decision/`, { decision: payload.decision, note: payload.note, content_hash: payload.content_hash })
    toasts.success(payload.decision === 'approve' ? 'Thanks! The shop will start the repair.' : 'Your answer was sent to the shop.')
    await queryClient.invalidateQueries({ queryKey: ['portal'] })
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not send your decision.'
    await order.refetch()
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div>
    <RouterLink :to="{ name: 'portal' }" class="text-sm text-slate-500 hover:underline">← My repairs</RouterLink>
    <LoadingState v-if="order.isPending.value" />
    <ErrorState v-else-if="order.isError.value" class="mt-4" :error="order.error.value" />
    <div v-else-if="o" class="mt-2 space-y-6">
      <header>
        <h1 class="text-xl font-semibold">{{ o.device }}</h1>
        <div class="mt-1 flex flex-wrap items-center gap-2 text-sm text-slate-600">
          <StatusBadge :status="o.status" data-testid="portal-order-status" />
          <span>{{ o.reference }} · {{ o.business_name }}</span>
          <span v-if="o.expected_completion_date">· expected {{ date(o.expected_completion_date) }}</span>
        </div>
        <p class="mt-3 text-sm whitespace-pre-line">{{ o.problem_description }}</p>
      </header>

      <section v-if="latest" class="card p-5">
        <EstimateReview :estimate="latest" :can-decide="latest.status === 'sent'" :busy="busy" :error="error" @decide="decide" />
      </section>

      <section v-if="invoices.length" class="card p-5">
        <h2 class="font-semibold">Invoices</h2>
        <ul class="mt-3 space-y-2 text-sm">
          <li v-for="i in invoices" :key="i.id" class="flex flex-wrap items-center justify-between gap-2">
            <span>{{ i.reference }} · {{ money(i.total, i.currency) }} · balance {{ money(i.balance_due, i.currency) }}</span>
            <AppButton size="sm" variant="secondary" @click="download(`/portal/invoices/${i.id}/pdf/`, `${i.reference}.pdf`)">Download PDF</AppButton>
          </li>
        </ul>
      </section>

      <section v-if="attachments.length" class="card p-5">
        <h2 class="font-semibold">Photos and documents</h2>
        <ul class="mt-3 space-y-1 text-sm">
          <li v-for="a in attachments" :key="a.id">
            <button type="button" class="text-brand-700 hover:underline" @click="download(`/portal/orders/${o.id}/attachments/${a.id}/download/`, a.original_name)">{{ a.caption || a.original_name }}</button>
          </li>
        </ul>
      </section>

      <section class="card p-5">
        <h2 class="font-semibold">Updates</h2>
        <ol class="mt-3 space-y-3 border-l border-slate-200 pl-4 text-sm">
          <li v-for="(e, i) in [...timeline].reverse()" :key="i">
            <p>{{ e.message }}</p>
            <p class="text-xs text-slate-500">{{ dateTime(e.created_at) }}</p>
          </li>
        </ol>
      </section>
    </div>
  </div>
</template>
