<script setup lang="ts">
import type { Component } from 'vue'
import type { RouteLocationNormalizedLoaded } from 'vue-router'

import ConfirmHost from '@/components/ui/ConfirmHost.vue'
import ToastHost from '@/components/ui/ToastHost.vue'
import AppLayout from '@/layouts/AppLayout.vue'
import AuthLayout from '@/layouts/AuthLayout.vue'
import PortalLayout from '@/layouts/PortalLayout.vue'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()
const LAYOUTS: Record<string, Component | null> = { app: AppLayout, auth: AuthLayout, portal: PortalLayout, bare: null }

function layoutFor(route: RouteLocationNormalizedLoaded) {
  return LAYOUTS[route.meta.layout ?? 'bare'] ?? null
}

/** Staff pages are keyed by workspace, so no component state survives a workspace switch. */
function keyFor(route: RouteLocationNormalizedLoaded) {
  return route.meta.layout === 'app' ? `${session.workspaceId}:${route.path}` : undefined
}
</script>

<template>
  <RouterView v-slot="{ Component, route }">
    <component :is="layoutFor(route)" v-if="layoutFor(route)">
      <component :is="Component" :key="keyFor(route)" />
    </component>
    <component :is="Component" v-else />
  </RouterView>
  <ToastHost />
  <ConfirmHost />
</template>
