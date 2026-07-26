<script setup lang="ts">
import { ref } from 'vue'

import { api } from '@/api/client'
import AppButton from '@/components/ui/AppButton.vue'
import FormAlert from '@/components/ui/FormAlert.vue'
import TextField from '@/components/ui/TextField.vue'
import { useApiForm } from '@/composables/useApiForm'

const form = useApiForm({ email: '' })
const sent = ref(false)

async function onSubmit() {
  const ok = await form.submit(async (values) => {
    await api.post('/auth/password-reset/', values)
    return true
  })
  if (ok) sent.value = true
}
</script>

<template>
  <div class="card p-6 sm:p-8">
    <h1 class="text-xl font-semibold">Reset your password</h1>
    <FormAlert
      v-if="sent"
      class="mt-4"
      tone="success"
      message="If an account exists for that address, we sent a link to choose a new password. The link expires in a few hours."
    />
    <form v-else class="mt-5 space-y-4" novalidate @submit.prevent="onSubmit">
      <p class="text-sm text-slate-600">Enter your email and we'll send you a reset link.</p>
      <FormAlert :message="form.generalError.value" />
      <TextField v-model="form.values.email" label="Email" type="email" autocomplete="email" required :error="form.fieldError('email')" />
      <AppButton type="submit" class="w-full" :loading="form.submitting.value">Send reset link</AppButton>
    </form>
    <p class="mt-6 text-center text-sm"><RouterLink :to="{ name: 'login' }" class="text-brand-700 hover:underline">Back to sign in</RouterLink></p>
  </div>
</template>
