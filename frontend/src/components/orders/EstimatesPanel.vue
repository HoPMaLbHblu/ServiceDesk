<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'
import { computed, ref } from 'vue'

import { ApiError, api } from '@/api/client'
import { useInvalidateWorkspace, useWorkspaceQueryKey } from '@/api/queries'
import type { Estimate, OrderDetail } from '@/api/types'
import AppButton from '@/components/ui/AppButton.vue'
import AppModal from '@/components/ui/AppModal.vue'
import FormAlert from '@/components/ui/FormAlert.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import TextAreaField from '@/components/ui/TextAreaField.vue'
import TextField from '@/components/ui/TextField.vue'
import { useApiForm } from '@/composables/useApiForm'
import { date, dateTime, label, money } from '@/lib/format'
import { useSessionStore } from '@/stores/session'
import { useToastStore } from '@/stores/toasts'

import EstimateEditor from './EstimateEditor.vue'

const props = defineProps<{ order: OrderDetail }>()
const session = useSessionStore()
const toasts = useToastStore()
const invalidate = useInvalidateWorkspace()

const estimates = useQuery({
  queryKey: useWorkspaceQueryKey('estimates', { order: props.order.id }),
  queryFn: () => api.get<Estimate[]>('/estimates/', { order__public_id: props.order.id }),
})

const sorted = computed(() => [...(estimates.data.value ?? [])].sort((a, b) => b.version - a.version))
const latest = computed(() => sorted.value[0] ?? null)
const history = computed(() => sorted.value.slice(1))
const canRevise = computed(
  () =>
    session.isManager &&
    ['diagnosing', 'awaiting_approval', 'in_progress'].includes(props.order.status ?? '') &&
    latest.value?.status !== 'draft',
)
const creating = ref(false)
const error = ref<string | null>(null)

async function createVersion() {
  creating.value = true
  error.value = null
  try {
    await api.post('/estimates/', { order: props.order.id })
    await invalidate()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not create the estimate.'
  } finally {
    creating.value = false
  }
}

const decision = ref<'approve' | 'reject' | null>(null)
const decisionForm = useApiForm({ customer_name: '', note: '' })
function openDecision(kind: 'approve' | 'reject') {
  decisionForm.reset({ customer_name: props.order.customer.name, note: '' })
  decision.value = kind
}
async function recordDecision() {
  const est = latest.value
  if (!est || !decision.value) return
  const ok = await decisionForm.submit((v) =>
    api.post(`/estimates/${est.id}/record_decision/`, { ...v, decision: decision.value, content_hash: est.content_hash }),
  )
  if (ok) {
    toasts.success(decision.value === 'approve' ? 'Approval recorded. The repair can start.' : 'Rejection recorded.')
    decision.value = null
    await invalidate()
  }
}
</script>

<template>
  <section class="card p-4" data-testid="estimates-panel">
    <div class="mb-3 flex items-center justify-between gap-2">
      <h2 class="font-semibold">Estimate</h2>
      <AppButton v-if="canRevise" size="sm" variant="secondary" :loading="creating" @click="createVersion">
        {{ latest ? 'Revise estimate' : 'Create estimate' }}
      </AppButton>
    </div>
    <FormAlert class="mb-3" :message="error" />

    <p v-if="estimates.isPending.value" class="text-sm text-slate-500">Loading…</p>
    <p v-else-if="!latest" class="text-sm text-slate-500">No estimate yet. Start the diagnosis, then create an estimate and send it for approval.</p>
    <template v-else>
      <div class="mb-3 flex flex-wrap items-center gap-2 text-sm">
        <span class="font-medium">Version {{ latest.version }}</span>
        <StatusBadge :status="latest.status ?? 'draft'" />
        <span v-if="latest.sent_at" class="text-slate-500">sent {{ dateTime(latest.sent_at) }}<template v-if="latest.valid_until">, valid until {{ date(latest.valid_until) }}</template></span>
      </div>

      <EstimateEditor v-if="latest.status === 'draft' && session.isManager" :key="latest.id + latest.updated_at" :estimate="latest" @sent="toasts.success('Estimate sent to the customer for approval.')" />

      <template v-else>
        <div class="overflow-x-auto">
          <table class="table-base">
            <thead>
              <tr><th scope="col">Item</th><th scope="col" class="text-right">Qty</th><th scope="col" class="text-right">Price</th><th scope="col" class="text-right">Total</th></tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
              <tr v-for="line in latest.lines" :key="line.id">
                <td>{{ line.description }} <span class="text-xs text-slate-500">{{ label(line.kind) }}<template v-if="!line.taxable"> · no tax</template></span></td>
                <td class="text-right tabular-nums">{{ line.quantity }}</td>
                <td class="text-right tabular-nums">{{ money(line.unit_price, latest.currency) }}</td>
                <td class="text-right tabular-nums">{{ money(line.line_total, latest.currency) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <dl class="mt-2 ml-auto max-w-xs space-y-1 text-sm">
          <div class="flex justify-between"><dt>Subtotal</dt><dd class="tabular-nums">{{ money(latest.subtotal, latest.currency) }}</dd></div>
          <div class="flex justify-between"><dt>Tax ({{ latest.tax_rate }}%)</dt><dd class="tabular-nums">{{ money(latest.tax_total, latest.currency) }}</dd></div>
          <div class="flex justify-between font-semibold"><dt>Total</dt><dd class="tabular-nums">{{ money(latest.total, latest.currency) }}</dd></div>
        </dl>
        <p v-if="latest.notes" class="mt-2 text-sm whitespace-pre-line text-slate-700">{{ latest.notes }}</p>
        <p v-if="latest.decided_at" class="mt-3 text-sm" :class="latest.status === 'approved' ? 'text-green-800' : 'text-red-800'">
          {{ latest.status === 'approved' ? 'Approved' : 'Declined' }} by {{ latest.decided_by_name }} ({{ latest.decision_channel }}) on {{ dateTime(latest.decided_at) }}<template v-if="latest.decision_note">: “{{ latest.decision_note }}”</template>
        </p>
        <div v-if="latest.status === 'sent' && session.isManager" class="mt-4 rounded-md bg-amber-50 p-3 text-sm text-amber-900">
          Waiting for the customer to approve via the emailed link or portal. If they answered in person or by phone, record it:
          <div class="mt-2 flex gap-2">
            <AppButton size="sm" @click="openDecision('approve')">Record approval</AppButton>
            <AppButton size="sm" variant="secondary" @click="openDecision('reject')">Record rejection</AppButton>
          </div>
        </div>
      </template>

      <details v-if="history.length" class="mt-4 text-sm">
        <summary class="cursor-pointer text-slate-600">Earlier versions ({{ history.length }})</summary>
        <ul class="mt-2 space-y-1">
          <li v-for="e in history" :key="e.id" class="flex justify-between">
            <span>Version {{ e.version }} · {{ money(e.total, e.currency) }}</span>
            <StatusBadge :status="e.status ?? 'draft'" />
          </li>
        </ul>
      </details>
    </template>

    <AppModal :open="!!decision" :title="decision === 'approve' ? 'Record customer approval' : 'Record customer rejection'" @close="decision = null">
      <form id="decision-form" class="space-y-3" @submit.prevent="recordDecision">
        <FormAlert :message="decisionForm.generalError.value" />
        <TextField v-model="decisionForm.values.customer_name" label="Customer name" required :error="decisionForm.fieldError('customer_name')" />
        <TextAreaField v-model="decisionForm.values.note" label="Note (how and when they decided)" :rows="2" />
      </form>
      <template #footer>
        <AppButton variant="secondary" @click="decision = null">Cancel</AppButton>
        <AppButton type="submit" form="decision-form" :variant="decision === 'reject' ? 'danger' : 'primary'" :loading="decisionForm.submitting.value">Record</AppButton>
      </template>
    </AppModal>
  </section>
</template>
