<script setup lang="ts">
import { ref } from 'vue'

import type { PublicEstimate, PublicEstimateLine } from '@/api/types'
import AppButton from '@/components/ui/AppButton.vue'
import FormAlert from '@/components/ui/FormAlert.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import { date, dateTime, money } from '@/lib/format'

/** Customer-facing estimate with approve and decline, used by the portal and the emailed link. */
const props = defineProps<{
  estimate: PublicEstimate
  canDecide: boolean
  askName?: boolean
  busy?: boolean
  error?: string | null
}>()
const emit = defineEmits<{ decide: [payload: { decision: 'approve' | 'reject'; note: string; name: string; content_hash: string }] }>()

const note = ref('')
const name = ref(props.estimate.customer_name)
const declining = ref(false)

function decide(decision: 'approve' | 'reject') {
  emit('decide', { decision, note: note.value, name: name.value, content_hash: props.estimate.content_hash })
}
const lines = () => props.estimate.lines as unknown as PublicEstimateLine[]
</script>

<template>
  <article class="space-y-4" data-testid="estimate-review">
    <header class="flex flex-wrap items-center justify-between gap-2">
      <div>
        <h2 class="text-lg font-semibold">Estimate for {{ estimate.device }}</h2>
        <p class="text-sm text-slate-600">{{ estimate.business_name }} · {{ estimate.order_reference }} · version {{ estimate.version }}</p>
      </div>
      <StatusBadge :status="estimate.status" />
    </header>
    <div class="overflow-x-auto rounded-md border border-slate-200">
      <table class="table-base">
        <thead><tr><th scope="col">Item</th><th scope="col" class="text-right">Qty</th><th scope="col" class="text-right">Price</th><th scope="col" class="text-right">Total</th></tr></thead>
        <tbody class="divide-y divide-slate-100 bg-white">
          <tr v-for="(l, i) in lines()" :key="i">
            <td>{{ l.description }}</td>
            <td class="text-right tabular-nums">{{ l.quantity }}</td>
            <td class="text-right tabular-nums">{{ money(l.unit_price, estimate.currency) }}</td>
            <td class="text-right tabular-nums">{{ money(l.line_total, estimate.currency) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <dl class="ml-auto max-w-xs space-y-1 text-sm">
      <div class="flex justify-between"><dt>Subtotal</dt><dd class="tabular-nums">{{ money(estimate.subtotal, estimate.currency) }}</dd></div>
      <div class="flex justify-between"><dt>Tax ({{ estimate.tax_rate }}%)</dt><dd class="tabular-nums">{{ money(estimate.tax_total, estimate.currency) }}</dd></div>
      <div class="flex justify-between text-base font-semibold"><dt>Total</dt><dd class="tabular-nums">{{ money(estimate.total, estimate.currency) }}</dd></div>
    </dl>
    <p v-if="estimate.notes" class="rounded-md bg-slate-50 p-3 text-sm whitespace-pre-line">{{ estimate.notes }}</p>

    <p v-if="estimate.decided_at" class="text-sm" :class="estimate.status === 'approved' ? 'text-green-800' : 'text-slate-700'">
      {{ estimate.status === 'approved' ? 'Approved' : 'Declined' }} by {{ estimate.decided_by_name }} on {{ dateTime(estimate.decided_at) }}.
    </p>

    <div v-else-if="canDecide" class="space-y-3 rounded-md border border-slate-200 bg-white p-4">
      <p class="text-sm text-slate-700">
        Please approve the work so we can start the repair<template v-if="estimate.valid_until"> (valid until {{ date(estimate.valid_until) }})</template>.
      </p>
      <FormAlert :message="error" />
      <div v-if="askName">
        <label for="approver-name" class="field-label">Your name</label>
        <input id="approver-name" v-model="name" class="field-input" autocomplete="name" required />
      </div>
      <div>
        <label for="decision-note" class="field-label">{{ declining ? 'Why are you declining? (optional)' : 'Message for the shop (optional)' }}</label>
        <textarea id="decision-note" v-model="note" rows="2" class="field-input" />
      </div>
      <div class="flex flex-wrap gap-2">
        <template v-if="!declining">
          <AppButton :loading="busy" :disabled="askName && !name.trim()" data-testid="approve-estimate" @click="decide('approve')">Approve {{ money(estimate.total, estimate.currency) }}</AppButton>
          <AppButton variant="secondary" :disabled="busy" @click="declining = true">Decline</AppButton>
        </template>
        <template v-else>
          <AppButton variant="danger" :loading="busy" :disabled="askName && !name.trim()" @click="decide('reject')">Decline estimate</AppButton>
          <AppButton variant="ghost" @click="declining = false">Back</AppButton>
        </template>
      </div>
    </div>
  </article>
</template>
