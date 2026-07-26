<script setup lang="ts">
import { ref } from 'vue'
import { useRoute } from 'vue-router'

import { api } from '@/api/client'
import AppButton from '@/components/ui/AppButton.vue'
import FormAlert from '@/components/ui/FormAlert.vue'
import TextField from '@/components/ui/TextField.vue'
import { useApiForm } from '@/composables/useApiForm'

const route = useRoute()
const uid = String(route.query.uid ?? '')
const token = String(route.query.token ?? '')
const form = useApiForm({ new_password: '' })
const done = ref(false)

async function onSubmit() {
  const ok = await form.submit(async (values) => {
    await api.post('/auth/password-reset/confirm/', { uid, token, new_password: values.new_password })
    return true
  })
  if (ok) done.value = true
}
</script>

<template>
  <div class="card p-6 sm:p-8">
    <h1 class="text-xl font-semibold">Choose a new password</h1>
    <template v-if="done">
      <FormAlert class="mt-4" tone="success" message="Your password was changed and other sessions were signed out." />
      <RouterLink :to="{ name: 'login' }" class="mt-4 inline-block text-sm font-medium text-brand-700 hover:underline">Sign in</RouterLink>
    </template>
    <FormAlert v-else-if="!uid || !token" class="mt-4" message="This reset link is incomplete. Request a new one." />
    <form v-else class="mt-5 space-y-4" novalidate @submit.prevent="onSubmit">
      <FormAlert :message="form.generalError.value">
        <RouterLink v-if="form.generalError.value" :to="{ name: 'forgot-password' }" class="ml-1 underline">Request a new link</RouterLink>
      </FormAlert>
      <TextField v-model="form.values.new_password" label="New password" type="password" autocomplete="new-password" required :error="form.fieldError('new_password')" />
      <AppButton type="submit" class="w-full" :loading="form.submitting.value">Save password</AppButton>
    </form>
  </div>
</template>
