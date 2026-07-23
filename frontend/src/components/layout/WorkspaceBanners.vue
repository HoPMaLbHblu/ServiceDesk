<script setup lang="ts">
import { computed, ref } from 'vue'

import { api } from '@/api/client'
import { useSubscription } from '@/api/queries'
import { useSessionStore } from '@/stores/session'
import { useToastStore } from '@/stores/toasts'

const session = useSessionStore()
const toasts = useToastStore()
const { data: subscription } = useSubscription()
const sending = ref(false)

const trialDaysLeft = computed(() => {
  const s = subscription.value
  if (!s || s.status !== 'trialing' || !s.trial_ends_at) return null
  return Math.max(0, Math.ceil((new Date(s.trial_ends_at).getTime() - Date.now()) / 86_400_000))
})

async function resend() {
  sending.value = true
  try {
    await api.post('/auth/resend-verification/')
    toasts.success('Verification email sent. Check your inbox.')
  } finally {
    sending.value = false
  }
}
</script>

<template>
  <div v-if="subscription && !subscription.can_write" role="alert" class="border-b border-amber-300 bg-amber-50 px-4 py-2 text-sm text-amber-900" data-testid="read-only-banner">
    <strong>Read-only workspace.</strong> {{ subscription.read_only_reason }}
    <RouterLink v-if="session.isOwner" :to="{ name: 'settings-billing' }" class="ml-1 font-medium underline">Manage billing</RouterLink>
    <span v-else> Ask the owner to update billing.</span>
  </div>
  <div v-else-if="trialDaysLeft !== null && trialDaysLeft <= 7 && session.isOwner" class="border-b border-blue-200 bg-blue-50 px-4 py-2 text-sm text-blue-900">
    Your trial ends in {{ trialDaysLeft }} day{{ trialDaysLeft === 1 ? '' : 's' }}.
    <RouterLink :to="{ name: 'settings-billing' }" class="font-medium underline">Choose a plan</RouterLink>
  </div>
  <div v-if="session.user && !session.user.email_verified" class="border-b border-slate-200 bg-white px-4 py-2 text-sm text-slate-700">
    Please verify {{ session.user.email }}. Invitations and plan changes need a verified address.
    <button type="button" class="ml-1 font-medium text-brand-700 underline disabled:opacity-50" :disabled="sending" @click="resend">Resend email</button>
  </div>
</template>
