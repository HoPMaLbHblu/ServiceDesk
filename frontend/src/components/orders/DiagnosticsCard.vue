<script setup lang="ts">
import { computed, ref } from 'vue'

import { api } from '@/api/client'
import { useInvalidateWorkspace } from '@/api/queries'
import type { OrderDetail } from '@/api/types'
import AppButton from '@/components/ui/AppButton.vue'
import FormAlert from '@/components/ui/FormAlert.vue'
import TextAreaField from '@/components/ui/TextAreaField.vue'
import { useApiForm } from '@/composables/useApiForm'
import { dateTime } from '@/lib/format'

const props = defineProps<{ order: OrderDetail }>()
const invalidate = useInvalidateWorkspace()
const editing = ref(false)
const form = useApiForm({ findings: '' })

const canEdit = computed(() => ['diagnosing', 'in_progress', 'awaiting_approval'].includes(props.order.status ?? ''))

function start() {
  form.reset({ findings: props.order.diagnostic_findings ?? '' })
  editing.value = true
}

async function save() {
  const ok = await form.submit((v) => api.post(`/orders/${props.order.id}/diagnostics/`, v))
  if (ok) {
    editing.value = false
    await invalidate()
  }
}
</script>

<template>
  <section class="card p-4">
    <div class="mb-2 flex items-center justify-between">
      <h2 class="font-semibold">Diagnosis</h2>
      <AppButton v-if="canEdit && !editing" size="sm" variant="ghost" @click="start">{{ order.diagnostic_findings ? 'Edit' : 'Record findings' }}</AppButton>
    </div>
    <form v-if="editing" class="space-y-2" @submit.prevent="save">
      <FormAlert :message="form.generalError.value" />
      <TextAreaField v-model="form.values.findings" label="Findings" :rows="4" :error="form.fieldError('findings')" />
      <div class="flex justify-end gap-2">
        <AppButton variant="secondary" size="sm" @click="editing = false">Cancel</AppButton>
        <AppButton type="submit" size="sm" :loading="form.submitting.value">Save findings</AppButton>
      </div>
    </form>
    <template v-else-if="order.diagnostic_findings">
      <p class="text-sm whitespace-pre-line">{{ order.diagnostic_findings }}</p>
      <p class="mt-1 text-xs text-slate-500">{{ order.diagnosed_by?.name }} · {{ dateTime(order.diagnosed_at) }}</p>
    </template>
    <p v-else class="text-sm text-slate-500">No findings recorded yet.</p>
  </section>
</template>
