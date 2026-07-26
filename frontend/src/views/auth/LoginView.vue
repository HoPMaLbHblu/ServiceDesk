<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import AppButton from '@/components/ui/AppButton.vue'
import FormAlert from '@/components/ui/FormAlert.vue'
import TextField from '@/components/ui/TextField.vue'
import { useApiForm } from '@/composables/useApiForm'
import { homeFor } from '@/router'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()
const route = useRoute()
const router = useRouter()
const form = useApiForm({ email: '', password: '' })

const expired = computed(() => route.query.expired === '1' || session.expired)
const next = computed(() => (typeof route.query.next === 'string' && route.query.next.startsWith('/') ? route.query.next : null))

async function onSubmit() {
  const ok = await form.submit(async (values) => {
    await session.login(values.email, values.password)
    return true
  })
  if (ok) await router.replace(next.value ?? homeFor(session))
}
</script>

<template>
  <div class="card p-6 sm:p-8">
    <h1 class="text-xl font-semibold">Sign in</h1>
    <p class="mt-1 text-sm text-slate-600">Welcome back. Sign in to your workspace or customer portal.</p>
    <FormAlert v-if="expired" class="mt-4" tone="warning" message="Your session has ended. Sign in again to continue." />
    <form class="mt-5 space-y-4" novalidate @submit.prevent="onSubmit">
      <FormAlert :message="form.generalError.value" />
      <TextField v-model="form.values.email" label="Email" type="email" autocomplete="email" required :error="form.fieldError('email')" />
      <TextField v-model="form.values.password" label="Password" type="password" autocomplete="current-password" required :error="form.fieldError('password')" />
      <div class="flex items-center justify-between text-sm">
        <RouterLink :to="{ name: 'forgot-password' }" class="text-brand-700 hover:underline">Forgot password?</RouterLink>
      </div>
      <AppButton type="submit" class="w-full" :loading="form.submitting.value">Sign in</AppButton>
    </form>
    <p class="mt-6 text-center text-sm text-slate-600">
      New to ServiceDesk?
      <RouterLink :to="{ name: 'register', query: route.query }" class="font-medium text-brand-700 hover:underline">Create an account</RouterLink>
    </p>
  </div>
</template>
