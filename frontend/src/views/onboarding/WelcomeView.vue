<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ApiError, api } from '@/api/client'
import type { Session } from '@/api/types'
import AppButton from '@/components/ui/AppButton.vue'
import FormAlert from '@/components/ui/FormAlert.vue'
import SelectField from '@/components/ui/SelectField.vue'
import TextField from '@/components/ui/TextField.vue'
import { useApiForm } from '@/composables/useApiForm'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()
const router = useRouter()
const route = useRoute()
const showCreate = ref(route.query.create === '1' || session.memberships.length === 0)
const switchError = ref<string | null>(null)

const browserZone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
const zones = computed(() => {
  const supported = (Intl as unknown as { supportedValuesOf?: (key: string) => string[] }).supportedValuesOf?.('timeZone') ?? [browserZone, 'UTC']
  return supported.map((z) => ({ value: z, label: z.replace(/_/g, ' ') }))
})
const currencies = ['USD', 'EUR', 'GBP', 'CAD', 'AUD', 'UAH', 'PLN'].map((c) => ({ value: c, label: c }))

const form = useApiForm({ name: '', timezone: browserZone, currency: 'USD', tax_rate: '0', phone: '', email: '' })

async function create() {
  const result = await form.submit((values) => api.post<Session>('/workspaces/', values))
  if (result) {
    session.apply(result)
    await router.replace({ name: 'dashboard' })
  }
}

async function open(businessId: string) {
  switchError.value = null
  try {
    await session.switchWorkspace(businessId)
    await router.replace({ name: 'dashboard' })
  } catch (error) {
    switchError.value = error instanceof ApiError ? error.message : 'Could not open the workspace.'
  }
}

async function logout() {
  await session.logout()
  await router.replace({ name: 'login' })
}
</script>

<template>
  <div class="space-y-4">
    <div v-if="session.memberships.length && !showCreate" class="card p-6">
      <h1 class="text-xl font-semibold">Choose a workspace</h1>
      <FormAlert class="mt-3" :message="switchError" />
      <ul class="mt-4 divide-y divide-slate-200 rounded-md border border-slate-200">
        <li v-for="m in session.memberships" :key="m.business_id">
          <button type="button" class="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-slate-50" @click="open(m.business_id)">
            <span class="font-medium">{{ m.business_name }}</span>
            <span class="text-sm text-slate-500">{{ m.role }}</span>
          </button>
        </li>
      </ul>
      <button type="button" class="mt-4 text-sm text-brand-700 hover:underline" @click="showCreate = true">Create a new workspace</button>
    </div>

    <div v-if="showCreate" class="card p-6">
      <h1 class="text-xl font-semibold">Set up your repair shop</h1>
      <p class="mt-1 text-sm text-slate-600">You'll be the owner. The 14-day trial includes every feature; no card needed.</p>
      <form class="mt-5 space-y-4" novalidate @submit.prevent="create">
        <FormAlert :message="form.generalError.value" />
        <TextField v-model="form.values.name" label="Business name" required :error="form.fieldError('name')" />
        <SelectField v-model="form.values.timezone" label="Timezone" :options="zones" required :error="form.fieldError('timezone')" />
        <div class="grid grid-cols-2 gap-3">
          <SelectField v-model="form.values.currency" label="Currency" :options="currencies" required :error="form.fieldError('currency')" />
          <TextField v-model="form.values.tax_rate" label="Tax rate (%)" inputmode="decimal" :error="form.fieldError('tax_rate')" />
        </div>
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <TextField v-model="form.values.phone" label="Phone" type="tel" :error="form.fieldError('phone')" />
          <TextField v-model="form.values.email" label="Shop email" type="email" :error="form.fieldError('email')" />
        </div>
        <div class="flex items-center justify-between gap-2">
          <button v-if="session.memberships.length" type="button" class="text-sm text-slate-600 hover:underline" @click="showCreate = false">Back</button>
          <span v-else />
          <AppButton type="submit" :loading="form.submitting.value">Create workspace</AppButton>
        </div>
      </form>
    </div>

    <div v-if="session.hasPortal" class="card p-4 text-sm">
      Looking for your repairs? <RouterLink :to="{ name: 'portal' }" class="font-medium text-brand-700 hover:underline">Open the customer portal</RouterLink>
    </div>
    <p class="text-center text-sm text-slate-500">
      Signed in as {{ session.user?.email }}. <button type="button" class="underline" @click="logout">Sign out</button>
    </p>
  </div>
</template>
