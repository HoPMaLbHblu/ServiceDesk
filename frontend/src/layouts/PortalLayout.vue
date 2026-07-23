<script setup lang="ts">
import { useRouter } from 'vue-router'

import { useSessionStore } from '@/stores/session'

const session = useSessionStore()
const router = useRouter()

async function logout() {
  await session.logout()
  await router.push({ name: 'login' })
}
</script>

<template>
  <div class="min-h-full">
    <header class="border-b border-slate-200 bg-white">
      <div class="mx-auto flex max-w-4xl items-center justify-between gap-3 px-4 py-3">
        <RouterLink :to="{ name: 'portal' }" class="font-semibold">ServiceDesk <span class="font-normal text-slate-500">· My repairs</span></RouterLink>
        <div class="flex items-center gap-3 text-sm">
          <RouterLink v-if="session.memberships.length" :to="{ name: 'dashboard' }" class="text-brand-700 hover:underline">Staff area</RouterLink>
          <span class="hidden text-slate-600 sm:inline">{{ session.user?.email }}</span>
          <button type="button" class="text-slate-700 hover:underline" @click="logout">Sign out</button>
        </div>
      </div>
    </header>
    <main class="mx-auto max-w-4xl px-4 py-6"><RouterView /></main>
  </div>
</template>
