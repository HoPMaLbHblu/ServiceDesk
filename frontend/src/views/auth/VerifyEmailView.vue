<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { ApiError, api } from '@/api/client'
import FormAlert from '@/components/ui/FormAlert.vue'
import LoadingState from '@/components/ui/LoadingState.vue'
import { homeFor } from '@/router'
import { useSessionStore } from '@/stores/session'

const route = useRoute()
const session = useSessionStore()
const state = ref<'loading' | 'done' | 'error'>('loading')
const message = ref('')

onMounted(async () => {
  try {
    await api.post('/auth/verify-email/', { token: String(route.query.token ?? '') })
    // Refresh the session so the "verify your email" banner disappears.
    await session.restore()
    state.value = 'done'
  } catch (error) {
    state.value = 'error'
    message.value = error instanceof ApiError ? error.message : 'Verification failed.'
  }
})
</script>

<template>
  <div class="card p-6 sm:p-8">
    <h1 class="text-xl font-semibold">Email verification</h1>
    <LoadingState v-if="state === 'loading'" label="Verifying…" />
    <template v-else-if="state === 'done'">
      <FormAlert class="mt-4" tone="success" message="Thanks, your email address is verified." />
      <RouterLink :to="session.isAuthenticated ? homeFor(session) : { name: 'login' }" class="mt-4 inline-block text-sm font-medium text-brand-700 hover:underline">Continue</RouterLink>
    </template>
    <FormAlert v-else class="mt-4" :message="message" />
  </div>
</template>
