<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'
import { computed, ref } from 'vue'

import { ApiError, api, download } from '@/api/client'
import { useInvalidateWorkspace, useWorkspaceQueryKey } from '@/api/queries'
import type { InvoiceDetail, Payment } from '@/api/types'
import AppButton from '@/components/ui/AppButton.vue'
import AppModal from '@/components/ui/AppModal.vue'
import ErrorState from '@/components/ui/ErrorState.vue'
import FormAlert from '@/components/ui/FormAlert.vue'
import LoadingState from '@/components/ui/LoadingState.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import SelectField from '@/components/ui/SelectField.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import TextAreaField from '@/components/ui/TextAreaField.vue'
import TextField from '@/components/ui/TextField.vue'
import { useApiForm } from '@/composables/useApiForm'
import { PAYMENT_METHODS, date, dateTime, idempotencyKey, label, money } from '@/lib/format'
import { useToastStore } from '@/stores/toasts'

const props = defineProps<{ id: string }>()
const toasts = useToastStore()
const invalidate = useInvalidateWorkspace()
const invoice = useQuery({
  queryKey: useWorkspaceQueryKey('invoice', props.id),
  queryFn: () => api.get<InvoiceDetail>(`/invoices/${props.id}/`),
})
const inv = computed(() => invoice.data.value)
const open = computed(() => inv.value?.status === 'issued')

// Payment: the idempotency key is created when the form opens and reused on retries,
// so a double submit or a lost response can never record the payment twice.
const paying = ref(false)
let paymentKey = ''
const payment = useApiForm({ amount: '', method: 'card', reference: '', note: '' })
function openPayment() {
  paymentKey = idempotencyKey()
  payment.reset({ amount: inv.value?.balance_due ?? '', method: 'card', reference: '', note: '' })
  paying.value = true
}
async function recordPayment() {
  const ok = await payment.submit((v) => api.post(`/invoices/${props.id}/payments/`, { ...v, idempotency_key: paymentKey }))
  if (ok) {
    paying.value = false
    toasts.success('Payment recorded')
    await invalidate()
  }
}

const refunding = ref<Payment | null>(null)
let refundKey = ''
const refund = useApiForm({ amount: '', reason: '', method: 'card' })
function openRefund(p: Payment) {
  refundKey = idempotencyKey()
  refund.reset({ amount: p.refundable, reason: '', method: p.method })
  refunding.value = p
}
async function recordRefund() {
  const p = refunding.value
  if (!p) return
  const ok = await refund.submit((v) => api.post(`/payments/${p.id}/refund/`, { ...v, idempotency_key: refundKey }))
  if (ok) {
    refunding.value = null
    toasts.success('Refund recorded')
    await invalidate()
  }
}

const voiding = ref(false)
const voidForm = useApiForm({ reason: '' })
async function voidInvoice() {
  const ok = await voidForm.submit((v) => api.post(`/invoices/${props.id}/void/`, v))
  if (ok) {
    voiding.value = false
    toasts.success('Invoice voided. You can issue a corrected one from the order.')
    await invalidate()
  }
}

async function pdf() {
  try {
    await download(`/invoices/${props.id}/pdf/`, `${inv.value?.reference ?? 'invoice'}.pdf`)
  } catch (e) {
    toasts.error(e instanceof ApiError ? e.message : 'Could not download the PDF.')
  }
}
</script>

<template>
  <div>
    <LoadingState v-if="invoice.isPending.value" />
    <ErrorState v-else-if="invoice.isError.value" :error="invoice.error.value" />
    <template v-else-if="inv">
      <PageHeader :title="`Invoice ${inv.reference}`">
        <template #breadcrumb><RouterLink :to="{ name: 'invoices' }" class="text-sm text-slate-500 hover:underline">← Invoices</RouterLink></template>
        <template #meta>
          <div class="mt-2 flex flex-wrap items-center gap-2 text-sm">
            <StatusBadge :status="inv.status === 'void' ? 'void' : inv.payment_status" kind="payment" data-testid="invoice-status" />
            <span>{{ inv.customer_name }} · <RouterLink :to="{ name: 'order', params: { id: inv.order } }" class="text-brand-700 hover:underline">{{ inv.order_reference }}</RouterLink></span>
          </div>
        </template>
        <template #actions>
          <AppButton variant="secondary" @click="pdf">Download PDF</AppButton>
          <AppButton v-if="open && Number(inv.balance_due) > 0" @click="openPayment">Record payment</AppButton>
          <AppButton v-if="open" variant="ghost" class="text-red-700" @click="voidForm.reset({ reason: '' }); voiding = true">Void</AppButton>
        </template>
      </PageHeader>

      <FormAlert v-if="inv.status === 'void'" class="mb-4" tone="warning" :message="`Voided ${dateTime(inv.voided_at)}: ${inv.void_reason}`" />

      <div class="grid gap-6 lg:grid-cols-3">
        <section class="card p-4 lg:col-span-2">
          <div class="mb-3 flex flex-wrap justify-between gap-2 text-sm text-slate-600">
            <span>Issued {{ date(inv.issued_at) }}<template v-if="inv.due_date"> · due {{ date(inv.due_date) }}</template></span>
            <span>From estimate v{{ inv.estimate_version }}</span>
          </div>
          <div class="overflow-x-auto">
            <table class="table-base">
              <thead><tr><th scope="col">Item</th><th scope="col" class="text-right">Qty</th><th scope="col" class="text-right">Price</th><th scope="col" class="text-right">Total</th></tr></thead>
              <tbody class="divide-y divide-slate-100">
                <tr v-for="l in inv.lines" :key="l.id">
                  <td>{{ l.description }} <span class="text-xs text-slate-500">{{ l.sku }}</span></td>
                  <td class="text-right tabular-nums">{{ l.quantity }}</td>
                  <td class="text-right tabular-nums">{{ money(l.unit_price, inv.currency) }}</td>
                  <td class="text-right tabular-nums">{{ money(l.line_total, inv.currency) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <dl class="mt-3 ml-auto max-w-xs space-y-1 text-sm">
            <div class="flex justify-between"><dt>Subtotal</dt><dd class="tabular-nums">{{ money(inv.subtotal, inv.currency) }}</dd></div>
            <div class="flex justify-between"><dt>Tax ({{ inv.tax_rate }}%)</dt><dd class="tabular-nums">{{ money(inv.tax_total, inv.currency) }}</dd></div>
            <div class="flex justify-between font-semibold"><dt>Total</dt><dd class="tabular-nums">{{ money(inv.total, inv.currency) }}</dd></div>
            <div class="flex justify-between"><dt>Paid</dt><dd class="tabular-nums">{{ money(inv.amount_paid, inv.currency) }}</dd></div>
            <div class="flex justify-between font-semibold"><dt>Balance due</dt><dd class="tabular-nums" data-testid="balance-due">{{ money(inv.balance_due, inv.currency) }}</dd></div>
          </dl>
        </section>

        <section class="card p-4">
          <h2 class="mb-3 font-semibold">Payments</h2>
          <p v-if="!inv.payments.length" class="text-sm text-slate-500">No payments yet.</p>
          <ul v-else class="space-y-3 text-sm">
            <li v-for="p in inv.payments" :key="p.id" class="flex items-start justify-between gap-2">
              <div>
                <p :class="['font-medium tabular-nums', p.kind === 'refund' ? 'text-red-700' : '']">
                  {{ p.kind === 'refund' ? '−' : '' }}{{ money(p.amount, inv.currency) }} <span class="font-normal text-slate-500">{{ label(p.method) }}</span>
                </p>
                <p class="text-xs text-slate-500">{{ dateTime(p.received_at) }} · {{ p.recorded_by_name }}<template v-if="p.reference"> · {{ p.reference }}</template></p>
                <p v-if="p.note" class="text-xs text-slate-600">{{ p.note }}</p>
              </div>
              <AppButton v-if="p.kind === 'payment' && Number(p.refundable) > 0" size="sm" variant="ghost" @click="openRefund(p)">Refund</AppButton>
            </li>
          </ul>
        </section>
      </div>

      <AppModal :open="paying" title="Record payment" @close="paying = false">
        <form id="payment-form" class="space-y-3" novalidate @submit.prevent="recordPayment">
          <FormAlert :message="payment.generalError.value" />
          <TextField v-model="payment.values.amount" label="Amount" inputmode="decimal" required :hint="`Balance due ${money(inv.balance_due, inv.currency)}`" :error="payment.fieldError('amount')" />
          <SelectField v-model="payment.values.method" label="Method" :options="PAYMENT_METHODS" />
          <TextField v-model="payment.values.reference" label="Reference (card slip, transfer ID)" />
          <TextField v-model="payment.values.note" label="Note" />
        </form>
        <template #footer>
          <AppButton variant="secondary" @click="paying = false">Cancel</AppButton>
          <AppButton type="submit" form="payment-form" :loading="payment.submitting.value">Record payment</AppButton>
        </template>
      </AppModal>

      <AppModal :open="!!refunding" title="Refund payment" @close="refunding = null">
        <form id="refund-form" class="space-y-3" novalidate @submit.prevent="recordRefund">
          <FormAlert :message="refund.generalError.value" />
          <TextField v-model="refund.values.amount" label="Amount" inputmode="decimal" required :hint="`Up to ${money(refunding?.refundable, inv.currency)}`" :error="refund.fieldError('amount')" />
          <SelectField v-model="refund.values.method" label="Refund method" :options="PAYMENT_METHODS" />
          <TextField v-model="refund.values.reason" label="Reason" required :error="refund.fieldError('reason')" />
        </form>
        <template #footer>
          <AppButton variant="secondary" @click="refunding = null">Cancel</AppButton>
          <AppButton type="submit" form="refund-form" variant="danger" :loading="refund.submitting.value">Record refund</AppButton>
        </template>
      </AppModal>

      <AppModal :open="voiding" title="Void invoice" @close="voiding = false">
        <form id="void-form" class="space-y-3" @submit.prevent="voidInvoice">
          <p class="text-sm text-slate-700">Voiding keeps the invoice for your records but it no longer counts as owed. Invoices with payments must be refunded first.</p>
          <FormAlert :message="voidForm.generalError.value" />
          <TextAreaField v-model="voidForm.values.reason" label="Reason" required :rows="2" :error="voidForm.fieldError('reason')" />
        </form>
        <template #footer>
          <AppButton variant="secondary" @click="voiding = false">Keep invoice</AppButton>
          <AppButton type="submit" form="void-form" variant="danger" :loading="voidForm.submitting.value">Void invoice</AppButton>
        </template>
      </AppModal>
    </template>
  </div>
</template>
