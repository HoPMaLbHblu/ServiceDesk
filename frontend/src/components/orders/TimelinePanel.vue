<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'

import { api } from '@/api/client'
import { useInvalidateWorkspace, useWorkspaceQueryKey } from '@/api/queries'
import type { OrderDetail, OrderEvent } from '@/api/types'
import AppButton from '@/components/ui/AppButton.vue'
import FormAlert from '@/components/ui/FormAlert.vue'
import { useApiForm } from '@/composables/useApiForm'
import { dateTime } from '@/lib/format'

const props = defineProps<{ order: OrderDetail }>()
const invalidate = useInvalidateWorkspace()
const timeline = useQuery({
  queryKey: useWorkspaceQueryKey('order', props.order.id, 'timeline'),
  queryFn: () => api.get<OrderEvent[]>(`/orders/${props.order.id}/timeline/`),
})
const form = useApiForm({ body: '', visible_to_customer: false })

async function addNote() {
  const ok = await form.submit((v) => api.post(`/orders/${props.order.id}/notes/`, v))
  if (ok) {
    form.reset({ body: '', visible_to_customer: false })
    await invalidate()
  }
}
</script>

<template>
  <section class="card p-4" data-testid="timeline">
    <h2 class="mb-3 font-semibold">Timeline</h2>
    <form class="mb-4 space-y-2" @submit.prevent="addNote">
      <label for="order-note" class="sr-only">Add a note</label>
      <textarea id="order-note" v-model="form.values.body" rows="2" class="field-input" placeholder="Add a note…" />
      <FormAlert :message="form.generalError.value" />
      <div class="flex items-center justify-between gap-2">
        <label class="flex items-center gap-1.5 text-sm text-slate-700">
          <input v-model="form.values.visible_to_customer" type="checkbox" /> Visible to customer
        </label>
        <AppButton type="submit" size="sm" variant="secondary" :loading="form.submitting.value" :disabled="!form.values.body.trim()">Add note</AppButton>
      </div>
    </form>
    <ol class="relative space-y-4 border-l border-slate-200 pl-4">
      <li v-for="e in timeline.data.value ?? []" :key="e.id" class="text-sm">
        <span :class="['absolute -left-1.5 mt-1.5 h-3 w-3 rounded-full border-2 border-white', e.visible_to_customer ? 'bg-brand-600' : 'bg-slate-400']" aria-hidden="true" />
        <p class="whitespace-pre-line">{{ e.message }}</p>
        <p class="text-xs text-slate-500">
          {{ e.actor_label || 'System' }} · {{ dateTime(e.created_at) }}
          <span v-if="e.kind === 'internal_note'" class="ml-1 rounded bg-slate-100 px-1">internal</span>
          <span v-else-if="e.visible_to_customer" class="ml-1 rounded bg-brand-50 px-1 text-brand-700">customer sees</span>
        </p>
      </li>
    </ol>
  </section>
</template>
