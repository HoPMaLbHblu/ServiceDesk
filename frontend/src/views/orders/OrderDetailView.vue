<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'

import { api } from '@/api/client'
import { useWorkspaceQueryKey } from '@/api/queries'
import type { OrderDetail } from '@/api/types'
import OrderAppointments from '@/components/appointments/OrderAppointments.vue'
import AttachmentsPanel from '@/components/orders/AttachmentsPanel.vue'
import DiagnosticsCard from '@/components/orders/DiagnosticsCard.vue'
import EstimatesPanel from '@/components/orders/EstimatesPanel.vue'
import OrderDetailsCard from '@/components/orders/OrderDetailsCard.vue'
import OrderInvoiceCard from '@/components/orders/OrderInvoiceCard.vue'
import OrderTransitions from '@/components/orders/OrderTransitions.vue'
import PartsPanel from '@/components/orders/PartsPanel.vue'
import TimelinePanel from '@/components/orders/TimelinePanel.vue'
import ErrorState from '@/components/ui/ErrorState.vue'
import LoadingState from '@/components/ui/LoadingState.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import { useSessionStore } from '@/stores/session'

const props = defineProps<{ id: string }>()
const session = useSessionStore()
const order = useQuery({
  queryKey: useWorkspaceQueryKey('order', props.id),
  queryFn: () => api.get<OrderDetail>(`/orders/${props.id}/`),
})
</script>

<template>
  <div>
    <LoadingState v-if="order.isPending.value" />
    <ErrorState v-else-if="order.isError.value" :error="order.error.value" :retry="order.refetch" />
    <template v-else-if="order.data.value">
      <PageHeader :title="`${order.data.value.reference} · ${order.data.value.device_label}`">
        <template #breadcrumb><RouterLink :to="{ name: 'orders' }" class="text-sm text-slate-500 hover:underline">← Repair orders</RouterLink></template>
        <template #meta>
          <div class="mt-2 flex flex-wrap items-center gap-2 text-sm">
            <StatusBadge :status="order.data.value.status ?? 'new'" data-testid="order-status" />
            <StatusBadge :status="order.data.value.payment_status ?? 'not_invoiced'" kind="payment" />
            <span class="text-slate-600">
              for
              <RouterLink :to="{ name: 'customer', params: { id: order.data.value.customer.id } }" class="font-medium text-brand-700 hover:underline">{{ order.data.value.customer.name }}</RouterLink>
              <template v-if="order.data.value.customer.phone"> · {{ order.data.value.customer.phone }}</template>
            </span>
          </div>
        </template>
      </PageHeader>

      <div class="mb-6"><OrderTransitions :order="order.data.value" /></div>

      <div class="grid gap-6 lg:grid-cols-3">
        <div class="space-y-6 lg:col-span-2">
          <OrderDetailsCard :order="order.data.value" />
          <DiagnosticsCard :order="order.data.value" />
          <EstimatesPanel :order="order.data.value" />
          <PartsPanel :order="order.data.value" />
          <AttachmentsPanel :order="order.data.value" />
        </div>
        <div class="space-y-6">
          <OrderInvoiceCard v-if="session.isManager" :order="order.data.value" />
          <OrderAppointments :order="order.data.value" />
          <TimelinePanel :order="order.data.value" />
        </div>
      </div>
    </template>
  </div>
</template>
