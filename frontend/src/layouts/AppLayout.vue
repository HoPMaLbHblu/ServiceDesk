<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import type { Role } from '@/api/types'
import WorkspaceBanners from '@/components/layout/WorkspaceBanners.vue'
import WorkspaceSwitcher from '@/components/layout/WorkspaceSwitcher.vue'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()
const router = useRouter()
const route = useRoute()
const menuOpen = ref(false)

const NAV: { name: string; label: string; roles?: Role[]; icon: string }[] = [
  { name: 'dashboard', label: 'Today', icon: 'M3 10l7-7 7 7v7a1 1 0 01-1 1h-4v-5H8v5H4a1 1 0 01-1-1z' },
  { name: 'orders', label: 'Repair orders', icon: 'M4 3h12v14H4zM7 7h6M7 10h6M7 13h4' },
  { name: 'appointments', label: 'Appointments', icon: 'M3 5h14v12H3zM3 8h14M7 3v4M13 3v4' },
  { name: 'customers', label: 'Customers', icon: 'M10 9a3 3 0 100-6 3 3 0 000 6zM4 17a6 6 0 0112 0' },
  { name: 'inventory', label: 'Inventory', icon: 'M3 6l7-3 7 3-7 3-7-3zm0 0v8l7 3 7-3V6' },
  { name: 'invoices', label: 'Invoices', roles: ['owner', 'manager'], icon: 'M5 3h10v14l-2-1-2 1-2-1-2 1-2-1zM8 7h4M8 10h4' },
  { name: 'reports', label: 'Reports', roles: ['owner'], icon: 'M4 16V9M10 16V4M16 16v-5' },
  { name: 'settings', label: 'Settings', icon: 'M10 13a3 3 0 100-6 3 3 0 000 6zM10 2v2M10 16v2M2 10h2M16 10h2' },
]

const nav = computed(() => NAV.filter((item) => !item.roles || item.roles.includes(session.role as Role)))

function isActive(name: string) {
  if (name === 'dashboard') return route.name === 'dashboard'
  const target = router.resolve({ name }).path
  return route.path === target || route.path.startsWith(`${target}/`)
}

watch(() => route.fullPath, () => (menuOpen.value = false))

async function logout() {
  await session.logout()
  await router.push({ name: 'login' })
}
</script>

<template>
  <div class="min-h-full lg:flex">
    <a href="#main" class="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded focus:bg-white focus:px-3 focus:py-2">Skip to content</a>

    <!-- Mobile top bar -->
    <header class="sticky top-0 z-30 flex items-center justify-between bg-slate-900 px-4 py-3 text-white lg:hidden">
      <span class="font-semibold">ServiceDesk</span>
      <span class="truncate px-2 text-sm text-slate-300">{{ session.workspace?.name }}</span>
      <button type="button" class="rounded p-1 hover:bg-slate-800" :aria-expanded="menuOpen" aria-controls="sidebar" aria-label="Menu" @click="menuOpen = !menuOpen">
        <svg viewBox="0 0 20 20" class="h-6 w-6" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M3 5h14M3 10h14M3 15h14" stroke-linecap="round" /></svg>
      </button>
    </header>

    <aside
      id="sidebar"
      :class="[
        'z-20 flex-col bg-slate-900 text-slate-200 lg:sticky lg:top-0 lg:flex lg:h-screen lg:w-60 lg:shrink-0',
        menuOpen ? 'fixed inset-x-0 top-[52px] bottom-0 flex overflow-y-auto' : 'hidden',
      ]"
    >
      <div class="hidden px-5 pt-5 pb-3 text-lg font-semibold text-white lg:block">ServiceDesk</div>
      <div class="px-4 py-3"><WorkspaceSwitcher /></div>
      <nav class="flex-1 space-y-0.5 px-2 py-2" aria-label="Main">
        <RouterLink
          v-for="item in nav"
          :key="item.name"
          :to="{ name: item.name }"
          :class="['flex items-center gap-3 rounded-md px-3 py-2 text-sm', isActive(item.name) ? 'bg-slate-800 font-medium text-white' : 'hover:bg-slate-800/60 hover:text-white']"
          :aria-current="isActive(item.name) ? 'page' : undefined"
        >
          <svg viewBox="0 0 20 20" class="h-5 w-5 shrink-0" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" aria-hidden="true"><path :d="item.icon" /></svg>
          {{ item.label }}
        </RouterLink>
      </nav>
      <div class="border-t border-slate-800 px-4 py-4 text-sm">
        <p class="truncate font-medium text-white">{{ session.user?.full_name }}</p>
        <p class="truncate text-xs text-slate-400">{{ session.user?.email }} · <span data-testid="current-role">{{ session.role }}</span></p>
        <div class="mt-3 flex gap-3 text-xs">
          <RouterLink v-if="session.hasPortal" :to="{ name: 'portal' }" class="text-slate-300 hover:text-white">My repairs</RouterLink>
          <button type="button" class="text-slate-300 hover:text-white" data-testid="logout" @click="logout">Sign out</button>
        </div>
      </div>
    </aside>

    <div class="min-w-0 flex-1">
      <WorkspaceBanners />
      <main id="main" class="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        <slot />
      </main>
    </div>
  </div>
</template>
