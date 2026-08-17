<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ApiError, api } from '@/api/client'
import AppButton from '@/components/ui/AppButton.vue'
import FormAlert from '@/components/ui/FormAlert.vue'
import { useSessionStore } from '@/stores/session'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const token = String(route.query.token ?? '')
const error = ref<string | null>(null)
const busy = ref(false)

async function accept() {
  busy.value = true
  error.value = null
  try {
    await api.post('/portal/accept/', { token })
    await session.restore()
    await router.replace({ name: 'portal' })
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not link your account.'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="card p-6 sm:p-8">
    <h1 class="text-xl font-semibold">Customer portal</h1>
    <p class="mt-2 text-sm text-slate-600">Follow your repairs, approve estimates and download invoices online.</p>
    <FormAlert v-if="!token" class="mt-4" message="This link is incomplete." />
    <template v-else-if="!session.isAuthenticated">
      <p class="mt-4 text-sm text-slate-700">Sign in, or create an account with the email address the invitation was sent to.</p>
      <div class="mt-4 flex gap-2">
        <RouterLink :to="{ name: 'login', query: { next: route.fullPath } }" class="rounded-md bg-brand-600 px-3.5 py-2 text-sm font-medium text-white">Sign in</RouterLink>
        <RouterLink :to="{ name: 'register', query: { next: route.fullPath } }" class="rounded-md border border-slate-300 px-3.5 py-2 text-sm font-medium">Create account</RouterLink>
      </div>
    </template>
    <template v-else>
      <FormAlert class="mt-4" :message="error" />
      <p class="mt-4 text-sm">Signed in as {{ session.user?.email }}.</p>
      <AppButton class="mt-3" :loading="busy" @click="accept">Connect my repairs</AppButton>
    </template>
  </div>
</template>
