<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import AppButton from '@/components/ui/AppButton.vue'
import FormAlert from '@/components/ui/FormAlert.vue'
import TextField from '@/components/ui/TextField.vue'
import { useApiForm } from '@/composables/useApiForm'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()
const route = useRoute()
const router = useRouter()
const form = useApiForm({ full_name: '', email: typeof route.query.email === 'string' ? route.query.email : '', password: '' })
const next = computed(() => (typeof route.query.next === 'string' && route.query.next.startsWith('/') ? route.query.next : null))

async function onSubmit() {
  const ok = await form.submit(async (values) => {
    await session.register(values)
    return true
  })
  if (ok) await router.replace(next.value ?? { name: 'welcome' })
}
</script>

<template>
  <div class="card p-6 sm:p-8">
    <h1 class="text-xl font-semibold">Create your account</h1>
    <p class="mt-1 text-sm text-slate-600">Start a 14-day trial for your repair shop, or join a team you were invited to.</p>
    <form class="mt-5 space-y-4" novalidate @submit.prevent="onSubmit">
      <FormAlert :message="form.generalError.value" />
      <TextField v-model="form.values.full_name" label="Full name" autocomplete="name" required :error="form.fieldError('full_name')" />
      <TextField v-model="form.values.email" label="Email" type="email" autocomplete="email" required :error="form.fieldError('email')" />
      <TextField
        v-model="form.values.password"
        label="Password"
        type="password"
        autocomplete="new-password"
        required
        hint="At least 10 characters. Avoid common passwords."
        :error="form.fieldError('password')"
      />
      <AppButton type="submit" class="w-full" :loading="form.submitting.value">Create account</AppButton>
    </form>
    <p class="mt-6 text-center text-sm text-slate-600">
      Already have an account?
      <RouterLink :to="{ name: 'login', query: route.query }" class="font-medium text-brand-700 hover:underline">Sign in</RouterLink>
    </p>
  </div>
</template>
