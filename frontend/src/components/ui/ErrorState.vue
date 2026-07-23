<script setup lang="ts">
import { computed } from 'vue'

import { ApiError } from '@/api/client'

import AppButton from './AppButton.vue'

const props = defineProps<{ error: unknown; retry?: () => void }>()

const message = computed(() => {
  const error = props.error
  if (error instanceof ApiError) {
    if (error.status === 404) return 'This record does not exist or you do not have access to it.'
    if (error.status === 403) return error.message || 'You do not have permission to view this.'
    return error.message
  }
  return 'Could not load data. Check your connection and try again.'
})
</script>

<template>
  <div role="alert" class="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-800">
    <p>{{ message }}</p>
    <AppButton v-if="retry" class="mt-3" size="sm" variant="secondary" @click="retry()">Try again</AppButton>
  </div>
</template>
