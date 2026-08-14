<script setup lang="ts">
import { onMounted } from 'vue'

import { api } from '@/api/client'
import AppButton from '@/components/ui/AppButton.vue'
import FormAlert from '@/components/ui/FormAlert.vue'
import TextField from '@/components/ui/TextField.vue'
import { useApiForm } from '@/composables/useApiForm'
import { useSessionStore } from '@/stores/session'
import { useToastStore } from '@/stores/toasts'

const session = useSessionStore()
const toasts = useToastStore()
const profile = useApiForm({ full_name: '' })
const password = useApiForm({ current_password: '', new_password: '' })

onMounted(() => profile.reset({ full_name: session.user?.full_name ?? '' }))

async function saveProfile() {
  const ok = await profile.submit((v) => api.patch('/auth/me/', v))
  if (ok) {
    await session.restore()
    toasts.success('Profile saved')
  }
}

async function changePassword() {
  const ok = await password.submit(async (v) => {
    await api.post('/auth/change-password/', v)
    return true
  })
  if (ok) {
    password.reset({ current_password: '', new_password: '' })
    toasts.success('Password changed. Other devices were signed out.')
  }
}
</script>

<template>
  <div class="grid max-w-3xl gap-6">
    <section class="card p-5">
      <h2 class="font-semibold">Profile</h2>
      <form class="mt-4 space-y-4" novalidate @submit.prevent="saveProfile">
        <FormAlert :message="profile.generalError.value" />
        <TextField v-model="profile.values.full_name" label="Full name" required :error="profile.fieldError('full_name')" />
        <p class="text-sm text-slate-600">
          Email: {{ session.user?.email }}
          <span :class="session.user?.email_verified ? 'text-green-700' : 'text-amber-800'">({{ session.user?.email_verified ? 'verified' : 'not verified' }})</span>
        </p>
        <AppButton type="submit" :loading="profile.submitting.value" :disabled="!profile.dirty.value">Save</AppButton>
      </form>
    </section>
    <section class="card p-5">
      <h2 class="font-semibold">Change password</h2>
      <form class="mt-4 space-y-4" novalidate @submit.prevent="changePassword">
        <FormAlert :message="password.generalError.value" />
        <TextField v-model="password.values.current_password" label="Current password" type="password" autocomplete="current-password" required :error="password.fieldError('current_password')" />
        <TextField v-model="password.values.new_password" label="New password" type="password" autocomplete="new-password" required :error="password.fieldError('new_password')" />
        <AppButton type="submit" :loading="password.submitting.value">Change password</AppButton>
      </form>
    </section>
  </div>
</template>
