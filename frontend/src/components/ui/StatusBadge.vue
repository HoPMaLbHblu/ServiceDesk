<script setup lang="ts">
import { computed } from 'vue'

import { PAYMENT_LABELS, STATUS_LABELS, label } from '@/lib/format'

import AppBadge from './AppBadge.vue'

const props = defineProps<{ status: string; kind?: 'order' | 'payment' | 'generic' }>()

const TONES: Record<string, 'gray' | 'blue' | 'green' | 'amber' | 'red' | 'purple' | 'teal'> = {
  new: 'gray',
  scheduled: 'blue',
  diagnosing: 'purple',
  awaiting_approval: 'amber',
  in_progress: 'blue',
  ready_for_pickup: 'teal',
  completed: 'green',
  cancelled: 'red',
  not_invoiced: 'gray',
  unpaid: 'amber',
  partially_paid: 'amber',
  paid: 'green',
  refunded: 'gray',
  draft: 'gray',
  sent: 'amber',
  approved: 'green',
  rejected: 'red',
  superseded: 'gray',
  issued: 'blue',
  void: 'red',
  pending: 'amber',
  sending: 'blue',
  failed: 'red',
  trialing: 'blue',
  active: 'green',
  past_due: 'amber',
  active_reservation: 'blue',
  consumed: 'green',
  released: 'gray',
  no_show: 'red',
}

const text = computed(() => {
  if (props.kind === 'payment') return PAYMENT_LABELS[props.status] ?? label(props.status)
  return STATUS_LABELS[props.status] ?? label(props.status)
})
</script>

<template>
  <AppBadge :tone="TONES[status] ?? 'gray'">{{ text }}</AppBadge>
</template>
