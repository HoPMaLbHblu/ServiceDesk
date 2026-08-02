<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import { ApiError, api } from '@/api/client'
import { useInvalidateWorkspace, useWorkspaceQueryKey } from '@/api/queries'
import type { InvoiceDetail, InvoiceList, OrderDetail, Paginated } from '@/api/types'
import AppButton from '@/components/ui/AppButton.vue'
import FormAlert from '@/components/ui/FormAlert.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import { money } from '@/lib/format'

const props = defineProps<{ order: OrderDetail }>()
const router = useRouter()
const invalidate = useInvalidateWorkspace()
const invoices = useQuery({
  queryKey: useWorkspaceQueryKey('invoices', { order: props.order.id }),
  queryFn: () => api.get<Paginated<InvoiceList>>('/invoices/', { order: props.order.id }),
})
const issued = computed(() => invoices.data.value?.results.find((i) => i.status === 'issued') ?? null)
const canIssue = computed(() => !issued.value && ['in_progress', 'ready_for_pickup'].includes(props.order.status ?? ''))
const busy = ref(false)
const error = ref<string | null>(null)

async function issue() {
  busy.value = true
  error.value = null
  try {
    const invoice = await api.post<InvoiceDetail>('/invoices/', { order: props.order.id, due_days: 14, notes: '' })
    await invalidate()
    await router.push({ name: 'invoice', params: { id: invoice.id } })
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not issue the invoice.'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <section class="card p-4">
    <h2 class="mb-2 font-semibold">Invoice</h2>
    <div v-if="issued" class="space-y-1 text-sm">
      <RouterLink :to="{ name: 'invoice', params: { id: issued.id } }" class="font-medium text-brand-700 hover:underline">{{ issued.reference }}</RouterLink>
      <p>{{ money(issued.total, issued.currency) }} · balance {{ money(issued.balance_due, issued.currency) }}</p>
      <StatusBadge :status="issued.payment_status" kind="payment" />
    </div>
    <template v-else>
      <p class="text-sm text-slate-600">
        {{ canIssue ? 'Issue the invoice from the approved estimate and the parts used.' : 'Available once the repair is in progress and the estimate is approved.' }}
      </p>
      <AppButton v-if="canIssue" class="mt-3" size="sm" :loading="busy" @click="issue">Issue invoice</AppButton>
      <FormAlert class="mt-2" :message="error" />
    </template>
  </section>
</template>
