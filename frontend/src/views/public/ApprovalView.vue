<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { ApiError, api } from '@/api/client'
import type { PublicEstimate } from '@/api/types'
import EstimateReview from '@/components/portal/EstimateReview.vue'
import ErrorState from '@/components/ui/ErrorState.vue'
import FormAlert from '@/components/ui/FormAlert.vue'
import LoadingState from '@/components/ui/LoadingState.vue'

const props = defineProps<{ token: string }>()
const estimate = ref<PublicEstimate | null>(null)
const loadError = ref<unknown>(null)
const busy = ref(false)
const error = ref<string | null>(null)
const done = ref<string | null>(null)

async function load() {
  try {
    estimate.value = await api.get<PublicEstimate>(`/public/approvals/${encodeURIComponent(props.token)}/`)
  } catch (e) {
    loadError.value = e
  }
}
onMounted(load)

async function decide(payload: { decision: 'approve' | 'reject'; note: string; name: string; content_hash: string }) {
  busy.value = true
  error.value = null
  try {
    estimate.value = await api.post<PublicEstimate>(`/public/approvals/${encodeURIComponent(props.token)}/`, payload)
    done.value = payload.decision === 'approve' ? 'Thank you. The shop has been notified and will start the repair.' : 'Thanks for letting us know. The shop has been notified.'
  } catch (e) {
    if (e instanceof ApiError && e.code === 'estimate_changed') {
      error.value = 'The shop changed this estimate after the link was sent. Please check your email for the latest version.'
    } else error.value = e instanceof ApiError ? e.message : 'Something went wrong. Please try again.'
  } finally {
    busy.value = false
  }
}

const stateMessages: Record<string, string> = {
  used: 'A decision was already recorded with this link.',
  expired: 'This estimate has expired. Contact the shop for an updated quote.',
  superseded: 'There is a newer version of this estimate. Check your email for the latest link.',
}
</script>

<template>
  <div class="card p-5 sm:p-6">
    <LoadingState v-if="!estimate && !loadError" />
    <ErrorState v-else-if="loadError" :error="loadError" />
    <template v-else-if="estimate">
      <FormAlert v-if="done" class="mb-4" tone="success" :message="done" />
      <FormAlert v-else-if="estimate.link_state && estimate.link_state !== 'open'" class="mb-4" tone="info" :message="stateMessages[estimate.link_state] ?? 'This link can no longer be used.'" />
      <EstimateReview :estimate="estimate" :can-decide="!done && estimate.link_state === 'open'" ask-name :busy="busy" :error="error" @decide="decide" />
    </template>
  </div>
</template>
