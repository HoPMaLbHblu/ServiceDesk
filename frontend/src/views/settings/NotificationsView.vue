<script setup lang="ts">
import { ref } from 'vue'

import { ApiError, api } from '@/api/client'
import { useInvalidateWorkspace } from '@/api/queries'
import type { Notification } from '@/api/types'
import AppButton from '@/components/ui/AppButton.vue'
import AppModal from '@/components/ui/AppModal.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import ErrorState from '@/components/ui/ErrorState.vue'
import LoadingState from '@/components/ui/LoadingState.vue'
import PaginationBar from '@/components/ui/PaginationBar.vue'
import SearchInput from '@/components/ui/SearchInput.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import { useListQuery } from '@/composables/useListQuery'
import { dateTime, label } from '@/lib/format'
import { useToastStore } from '@/stores/toasts'

const toasts = useToastStore()
const invalidate = useInvalidateWorkspace()
const { search, page, filters, query } = useListQuery<Notification>('notifications', '/notifications/', ['status'])
const viewing = ref<Notification | null>(null)

async function retry(n: Notification) {
  try {
    await api.post(`/notifications/${n.id}/retry/`)
    toasts.success('Queued for another attempt')
  } catch (e) {
    toasts.error(e instanceof ApiError ? e.message : 'Could not retry.')
  } finally {
    await invalidate()
  }
}
</script>

<template>
  <div>
    <p class="mb-4 max-w-2xl text-sm text-slate-600">Every email the workspace sends goes through this outbox. Failed deliveries are retried automatically with increasing delays.</p>
    <div class="mb-3 flex flex-col gap-2 sm:flex-row">
      <SearchInput v-model="search" label="Search emails" placeholder="Recipient or subject" />
      <select v-model="filters.status" class="field-input sm:max-w-40" aria-label="Status">
        <option value="">Any status</option>
        <option v-for="s in ['pending', 'sending', 'sent', 'failed']" :key="s" :value="s">{{ label(s) }}</option>
      </select>
    </div>
    <div class="card overflow-hidden">
      <LoadingState v-if="query.isPending.value" />
      <ErrorState v-else-if="query.isError.value" class="m-4" :error="query.error.value" />
      <EmptyState v-else-if="!query.data.value?.results.length" title="No emails" />
      <template v-else>
        <ul class="divide-y divide-slate-100">
          <li v-for="n in query.data.value.results" :key="n.id" class="flex flex-wrap items-center justify-between gap-2 px-4 py-3 text-sm">
            <button type="button" class="min-w-0 flex-1 text-left" @click="viewing = n">
              <p class="truncate font-medium">{{ n.subject }}</p>
              <p class="truncate text-slate-500">{{ n.recipient_email }} · {{ label(n.kind) }} · {{ dateTime(n.created_at) }}</p>
              <p v-if="n.last_error" class="truncate text-xs text-red-700">Attempt {{ n.attempts }}/{{ n.max_attempts }}: {{ n.last_error }}</p>
            </button>
            <div class="flex items-center gap-2">
              <StatusBadge :status="n.status ?? 'pending'" />
              <AppButton v-if="n.status === 'failed'" size="sm" variant="secondary" @click="retry(n)">Retry</AppButton>
            </div>
          </li>
        </ul>
        <PaginationBar v-model:page="page" :total-pages="query.data.value.total_pages" :count="query.data.value.count" />
      </template>
    </div>
    <AppModal :open="!!viewing" :title="viewing?.subject ?? ''" size="lg" @close="viewing = null">
      <p class="mb-2 text-sm text-slate-600">To {{ viewing?.recipient_email }}</p>
      <pre class="text-sm whitespace-pre-wrap">{{ viewing?.body }}</pre>
    </AppModal>
  </div>
</template>
