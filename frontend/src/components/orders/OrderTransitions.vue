<script setup lang="ts">
import { ref } from 'vue'

import { ApiError, api } from '@/api/client'
import { useInvalidateWorkspace } from '@/api/queries'
import type { OrderDetail } from '@/api/types'
import AppButton from '@/components/ui/AppButton.vue'
import AppModal from '@/components/ui/AppModal.vue'
import FormAlert from '@/components/ui/FormAlert.vue'
import TextAreaField from '@/components/ui/TextAreaField.vue'
import { STATUS_LABELS } from '@/lib/format'
import { useToastStore } from '@/stores/toasts'

const props = defineProps<{ order: OrderDetail }>()
const invalidate = useInvalidateWorkspace()
const toasts = useToastStore()
const busy = ref<string | null>(null)
const error = ref<string | null>(null)
const cancelOpen = ref(false)
const reason = ref('')

const ACTION_LABELS: Record<string, string> = {
  new: 'Back to new',
  diagnosing: 'Start diagnosis',
  in_progress: 'Start repair',
  ready_for_pickup: 'Mark ready for pickup',
  completed: 'Complete (picked up)',
  cancelled: 'Cancel order',
}

async function move(to: string, cancelReason = '') {
  busy.value = to
  error.value = null
  try {
    await api.post(`/orders/${props.order.id}/transition/`, { to_status: to, reason: cancelReason })
    toasts.success(`Order moved to ${STATUS_LABELS[to]}`)
    cancelOpen.value = false
    reason.value = ''
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not change the status.'
  } finally {
    busy.value = null
    // Refresh even after a refusal: a 409 usually means someone else changed the order.
    await invalidate()
  }
}
</script>

<template>
  <div v-if="order.allowed_transitions.length" class="space-y-2">
    <div class="flex flex-wrap gap-2" data-testid="transitions">
      <template v-for="to in order.allowed_transitions" :key="to">
        <AppButton v-if="to === 'cancelled'" variant="ghost" class="text-red-700" @click="cancelOpen = true">{{ ACTION_LABELS[to] }}</AppButton>
        <AppButton v-else :variant="to === 'new' ? 'secondary' : 'primary'" :loading="busy === to" :disabled="!!busy" @click="move(to)">
          {{ ACTION_LABELS[to] ?? STATUS_LABELS[to] }}
        </AppButton>
      </template>
    </div>
    <FormAlert :message="error" />
    <AppModal :open="cancelOpen" title="Cancel this order?" @close="cancelOpen = false">
      <p class="mb-3 text-sm text-slate-700">Reserved parts go back to stock and booked appointments are cancelled. The customer is notified.</p>
      <TextAreaField v-model="reason" label="Reason" required :rows="2" />
      <template #footer>
        <AppButton variant="secondary" @click="cancelOpen = false">Keep order</AppButton>
        <AppButton variant="danger" :loading="busy === 'cancelled'" :disabled="!reason.trim()" @click="move('cancelled', reason)">Cancel order</AppButton>
      </template>
    </AppModal>
  </div>
</template>
