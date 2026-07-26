<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ApiError, api } from '@/api/client'
import type { Session } from '@/api/types'
import AppButton from '@/components/ui/AppButton.vue'
import ErrorState from '@/components/ui/ErrorState.vue'
import FormAlert from '@/components/ui/FormAlert.vue'
import LoadingState from '@/components/ui/LoadingState.vue'
import { useSessionStore } from '@/stores/session'

type Preview = { business_name: string; email: string; role: string; status: string }

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const token = String(route.query.token ?? '')
const error = ref<string | null>(null)
const accepting = ref(false)

const preview = useQuery({
  queryKey: ['invitation-preview', token],
  queryFn: () => api.post<Preview>('/invitations/preview/', { token }),
  enabled: !!token,
})

async function accept() {
  accepting.value = true
  error.value = null
  try {
    session.apply(await api.post<Session>('/invitations/accept/', { token }))
    await router.replace({ name: 'dashboard' })
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not accept the invitation.'
  } finally {
    accepting.value = false
  }
}

async function signOutAndSwitch() {
  await session.logout()
  await router.replace({ name: 'login', query: { next: route.fullPath } })
}
</script>

<template>
  <div class="card p-6 sm:p-8">
    <h1 class="text-xl font-semibold">Join a workspace</h1>
    <FormAlert v-if="!token" class="mt-4" message="This invitation link is incomplete." />
    <LoadingState v-else-if="preview.isPending.value" />
    <ErrorState v-else-if="preview.isError.value" class="mt-4" :error="preview.error.value" />
    <template v-else-if="preview.data.value">
      <p class="mt-3 text-sm text-slate-700">
        You were invited to join <strong>{{ preview.data.value.business_name }}</strong> as
        <strong>{{ preview.data.value.role }}</strong> ({{ preview.data.value.email }}).
      </p>
      <FormAlert v-if="preview.data.value.status !== 'pending'" class="mt-4" :message="`This invitation is ${preview.data.value.status}. Ask the owner for a new one.`" />
      <template v-else-if="!session.isAuthenticated">
        <p class="mt-4 text-sm text-slate-600">Sign in or create an account with {{ preview.data.value.email }} to accept.</p>
        <div class="mt-4 flex gap-2">
          <RouterLink :to="{ name: 'login', query: { next: route.fullPath } }" class="rounded-md bg-brand-600 px-3.5 py-2 text-sm font-medium text-white">Sign in</RouterLink>
          <RouterLink :to="{ name: 'register', query: { next: route.fullPath, email: preview.data.value.email } }" class="rounded-md border border-slate-300 px-3.5 py-2 text-sm font-medium">Create account</RouterLink>
        </div>
      </template>
      <template v-else>
        <FormAlert class="mt-4" :message="error" />
        <FormAlert
          v-if="session.user && session.user.email.toLowerCase() !== preview.data.value.email.toLowerCase()"
          class="mt-4"
          tone="warning"
          :message="`You are signed in as ${session.user.email}. This invitation is for ${preview.data.value.email}.`"
        >
          <button type="button" class="ml-1 underline" @click="signOutAndSwitch">Sign in with another account</button>
        </FormAlert>
        <AppButton v-else class="mt-4" :loading="accepting" @click="accept">Accept invitation</AppButton>
      </template>
    </template>
  </div>
</template>
