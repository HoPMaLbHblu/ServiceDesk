<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'
import { ref } from 'vue'

import { ApiError, api, download, request } from '@/api/client'
import { useInvalidateWorkspace, useWorkspaceQueryKey } from '@/api/queries'
import type { Attachment, OrderDetail } from '@/api/types'
import AppButton from '@/components/ui/AppButton.vue'
import FormAlert from '@/components/ui/FormAlert.vue'
import { dateTime, fileSize } from '@/lib/format'

const props = defineProps<{ order: OrderDetail }>()
const invalidate = useInvalidateWorkspace()
const attachments = useQuery({
  queryKey: useWorkspaceQueryKey('order', props.order.id, 'attachments'),
  queryFn: () => api.get<Attachment[]>(`/orders/${props.order.id}/attachments/`),
})

const file = ref<File | null>(null)
const caption = ref('')
const visible = ref(false)
const uploading = ref(false)
const error = ref<string | null>(null)
const input = ref<HTMLInputElement | null>(null)

async function upload() {
  if (!file.value) return
  uploading.value = true
  error.value = null
  const body = new FormData()
  body.append('file', file.value)
  body.append('caption', caption.value)
  body.append('visible_to_customer', String(visible.value))
  try {
    await request('POST', `/orders/${props.order.id}/attachments/`, { body })
    file.value = null
    caption.value = ''
    visible.value = false
    if (input.value) input.value.value = ''
    await invalidate()
  } catch (e) {
    error.value = e instanceof ApiError ? (e.fields.file?.[0] ?? e.message) : 'Upload failed.'
  } finally {
    uploading.value = false
  }
}

function get(a: Attachment) {
  void download(`/orders/${props.order.id}/attachments/${a.id}/download/`, a.original_name)
}
</script>

<template>
  <section class="card p-4">
    <h2 class="mb-3 font-semibold">Photos and files</h2>
    <p v-if="!attachments.data.value?.length" class="text-sm text-slate-500">Nothing uploaded yet.</p>
    <ul v-else class="mb-4 divide-y divide-slate-100 text-sm">
      <li v-for="a in attachments.data.value" :key="a.id" class="flex items-center justify-between gap-2 py-2">
        <div class="min-w-0">
          <button type="button" class="truncate font-medium text-brand-700 hover:underline" @click="get(a)">{{ a.original_name }}</button>
          <p class="text-xs text-slate-500">
            {{ a.caption ? `${a.caption} · ` : '' }}{{ fileSize(a.size) }} · {{ a.uploaded_by_name }} · {{ dateTime(a.created_at) }}
          </p>
        </div>
        <span :class="['shrink-0 text-xs', a.visible_to_customer ? 'text-green-700' : 'text-slate-500']">{{ a.visible_to_customer ? 'Customer can see' : 'Internal' }}</span>
      </li>
    </ul>
    <form class="space-y-2" @submit.prevent="upload">
      <label for="attachment-file" class="field-label">Upload (JPEG, PNG, WebP, HEIC or PDF, up to 10 MB)</label>
      <input
        id="attachment-file"
        ref="input"
        type="file"
        accept="image/jpeg,image/png,image/webp,image/heic,application/pdf"
        class="block w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-slate-100 file:px-3 file:py-1.5 file:text-sm"
        @change="file = ($event.target as HTMLInputElement).files?.[0] ?? null"
      />
      <div v-if="file" class="flex flex-col gap-2 sm:flex-row sm:items-center">
        <input v-model="caption" class="field-input flex-1" placeholder="Caption (optional)" aria-label="Caption" />
        <label class="flex items-center gap-1.5 text-sm"><input v-model="visible" type="checkbox" /> Show to customer</label>
        <AppButton type="submit" size="sm" :loading="uploading">Upload</AppButton>
      </div>
      <FormAlert :message="error" />
    </form>
  </section>
</template>
