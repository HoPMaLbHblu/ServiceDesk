<script setup lang="ts">
import { ref } from 'vue'

import { ApiError, api } from '@/api/client'
import { useSubscription } from '@/api/queries'
import AppBadge from '@/components/ui/AppBadge.vue'
import AppButton from '@/components/ui/AppButton.vue'
import ErrorState from '@/components/ui/ErrorState.vue'
import FormAlert from '@/components/ui/FormAlert.vue'
import LoadingState from '@/components/ui/LoadingState.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import { date, money } from '@/lib/format'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()
const subscription = useSubscription()
const error = ref<string | null>(null)
const busy = ref<string | null>(null)

/** Follow a provider URL: Stripe Checkout in Stripe mode, or the in-app development checkout. */
function go(url: string) {
  const target = new URL(url, window.location.origin)
  window.location.assign(target.origin === window.location.origin ? target.pathname + target.search : target.href)
}

async function choose(plan: string) {
  busy.value = plan
  error.value = null
  try {
    go((await api.post<{ url: string }>('/billing/checkout/', { plan })).url)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not start checkout.'
  } finally {
    busy.value = null
  }
}

async function manage() {
  busy.value = 'portal'
  error.value = null
  try {
    go((await api.post<{ url: string }>('/billing/portal/')).url)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not open billing management.'
  } finally {
    busy.value = null
  }
}

const limit = (n: number | null | undefined, unit: string) => (n === null || n === undefined ? `Unlimited ${unit}` : `${n} ${unit}`)
</script>

<template>
  <div class="max-w-4xl">
    <LoadingState v-if="subscription.isPending.value" />
    <ErrorState v-else-if="subscription.isError.value" :error="subscription.error.value" />
    <template v-else-if="subscription.data.value">
      <section class="card p-5">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <h2 class="font-semibold">Subscription</h2>
          <AppBadge v-if="subscription.data.value.provider === 'dev'" tone="purple">{{ subscription.data.value.provider_label }}</AppBadge>
        </div>
        <div class="mt-3 flex flex-wrap items-center gap-2 text-sm">
          <span class="font-medium">{{ subscription.data.value.plan?.name ?? 'No plan' }}</span>
          <StatusBadge :status="subscription.data.value.status" data-testid="subscription-status" />
          <span v-if="subscription.data.value.status === 'trialing' && subscription.data.value.trial_ends_at" class="text-slate-600">trial ends {{ date(subscription.data.value.trial_ends_at) }}</span>
          <span v-else-if="subscription.data.value.current_period_end" class="text-slate-600">
            {{ subscription.data.value.cancel_at_period_end ? 'ends' : 'renews' }} {{ date(subscription.data.value.current_period_end) }}
          </span>
        </div>
        <FormAlert v-if="!subscription.data.value.can_write" class="mt-3" tone="warning" :message="`The workspace is read-only: ${subscription.data.value.read_only_reason}`" />
        <p class="mt-3 text-sm text-slate-600">
          Usage: {{ subscription.data.value.usage.staff }} team members, {{ subscription.data.value.usage.orders_this_month }} repair orders this month.
        </p>
        <FormAlert class="mt-3" :message="error" />
        <AppButton v-if="session.isOwner && subscription.data.value.status !== 'trialing'" class="mt-3" variant="secondary" :loading="busy === 'portal'" @click="manage">
          Manage payment method
        </AppButton>
        <p v-if="!session.isOwner" class="mt-3 text-sm text-slate-500">Only owners can change the plan.</p>
      </section>

      <section v-if="session.isOwner" class="mt-6 grid gap-4 sm:grid-cols-3">
        <div v-for="plan in subscription.data.value.plans" :key="plan.code" :class="['card flex flex-col p-5', subscription.data.value.plan?.code === plan.code ? 'ring-2 ring-brand-600' : '']">
          <h3 class="font-semibold">{{ plan.name }}</h3>
          <p class="mt-1 text-2xl font-semibold">{{ money(plan.price_monthly, plan.currency) }}<span class="text-sm font-normal text-slate-500">/month</span></p>
          <ul class="mt-3 flex-1 space-y-1 text-sm text-slate-700">
            <li>{{ limit(plan.max_staff, 'team members') }}</li>
            <li>{{ limit(plan.max_orders_per_month, 'repair orders a month') }}</li>
          </ul>
          <AppButton
            class="mt-4"
            :variant="subscription.data.value.plan?.code === plan.code && subscription.data.value.status === 'active' ? 'secondary' : 'primary'"
            :disabled="subscription.data.value.plan?.code === plan.code && subscription.data.value.status === 'active'"
            :loading="busy === plan.code"
            @click="choose(plan.code)"
          >
            {{ subscription.data.value.plan?.code === plan.code && subscription.data.value.status === 'active' ? 'Current plan' : `Choose ${plan.name}` }}
          </AppButton>
        </div>
      </section>
    </template>
  </div>
</template>
