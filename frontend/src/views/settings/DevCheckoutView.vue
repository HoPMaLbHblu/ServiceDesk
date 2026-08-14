<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ApiError, api } from '@/api/client'
import { useInvalidateWorkspace, useSubscription } from '@/api/queries'
import AppButton from '@/components/ui/AppButton.vue'
import FormAlert from '@/components/ui/FormAlert.vue'
import { useToastStore } from '@/stores/toasts'

const route = useRoute()
const router = useRouter()
const toasts = useToastStore()
const invalidate = useInvalidateWorkspace()
const subscription = useSubscription()
const plan = String(route.query.plan ?? '')
const busy = ref<string | null>(null)
const error = ref<string | null>(null)

async function simulate(action: 'activate' | 'payment_failed' | 'payment_succeeded' | 'cancel') {
  busy.value = action
  error.value = null
  try {
    await api.post('/billing/dev/', { action, plan: action === 'activate' ? plan : undefined })
    await invalidate()
    toasts.success('Billing event processed')
    if (action === 'activate') await router.push({ name: 'settings-billing' })
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'The simulated event failed.'
  } finally {
    busy.value = null
  }
}
</script>

<template>
  <div class="card max-w-xl p-6">
    <p class="inline-block rounded bg-purple-100 px-2 py-0.5 text-xs font-medium text-purple-800">Development billing · no real payment</p>
    <h2 class="mt-3 text-lg font-semibold">Simulated checkout</h2>
    <p class="mt-1 text-sm text-slate-600">
      This screen stands in for the payment provider. Each button sends a synthetic provider event through the same webhook processing used with Stripe.
    </p>
    <FormAlert class="mt-3" :message="error" />
    <div class="mt-4 space-y-3">
      <AppButton v-if="plan" class="w-full" :loading="busy === 'activate'" @click="simulate('activate')">Pay and activate the {{ plan }} plan</AppButton>
      <div class="grid grid-cols-1 gap-2 sm:grid-cols-3">
        <AppButton variant="secondary" :loading="busy === 'payment_failed'" @click="simulate('payment_failed')">Renewal fails</AppButton>
        <AppButton variant="secondary" :loading="busy === 'payment_succeeded'" @click="simulate('payment_succeeded')">Renewal paid</AppButton>
        <AppButton variant="danger" :loading="busy === 'cancel'" @click="simulate('cancel')">Cancel subscription</AppButton>
      </div>
    </div>
    <p class="mt-4 text-sm text-slate-600">Current status: <strong>{{ subscription.data.value?.status ?? '…' }}</strong></p>
    <RouterLink :to="{ name: 'settings-billing' }" class="mt-2 inline-block text-sm text-brand-700 hover:underline">Back to billing</RouterLink>
  </div>
</template>
