<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'
import { computed, ref } from 'vue'

import { ApiError, api } from '@/api/client'
import { useInvalidateWorkspace, useWorkspaceQueryKey } from '@/api/queries'
import type { OrderDetail, Paginated, Part, Reservation } from '@/api/types'
import AppButton from '@/components/ui/AppButton.vue'
import FormAlert from '@/components/ui/FormAlert.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import { idempotencyKey } from '@/lib/format'
import { useToastStore } from '@/stores/toasts'

const props = defineProps<{ order: OrderDetail }>()
const toasts = useToastStore()
const invalidate = useInvalidateWorkspace()

const reservations = useQuery({
  queryKey: useWorkspaceQueryKey('reservations', { order: props.order.id }),
  queryFn: () => api.get<Reservation[]>('/reservations/', { order__public_id: props.order.id }),
})
const parts = useQuery({
  queryKey: useWorkspaceQueryKey('parts', { is_active: true, page_size: 100, picker: true }),
  queryFn: () => api.get<Paginated<Part>>('/parts/', { is_active: true, page_size: 100 }),
})

const open = computed(() => !['completed', 'cancelled'].includes(props.order.status ?? ''))
const partId = ref('')
const quantity = ref('1')
const error = ref<string | null>(null)
const busy = ref<string | null>(null)
// One key per reservation attempt: a double click or a retried request cannot reserve twice.
let attemptKey = idempotencyKey()

async function reserve() {
  if (!partId.value) return
  busy.value = 'reserve'
  error.value = null
  try {
    await api.post('/reservations/', { order: props.order.id, part: partId.value, quantity: quantity.value, idempotency_key: attemptKey })
    attemptKey = idempotencyKey()
    partId.value = ''
    quantity.value = '1'
    await invalidate()
  } catch (e) {
    if (e instanceof ApiError) {
      const available = e.details.available
      error.value = e.code === 'insufficient_stock' && available !== undefined ? `${e.message} Available now: ${String(available)}.` : (Object.values(e.fields)[0]?.[0] ?? e.message)
    } else error.value = 'Could not reserve the part.'
  } finally {
    busy.value = null
  }
}

async function act(reservation: Reservation, action: 'consume' | 'release') {
  busy.value = reservation.id
  try {
    await api.post(`/reservations/${reservation.id}/${action}/`)
    toasts.success(action === 'consume' ? `${reservation.part_name} marked as used` : `${reservation.part_name} returned to stock`)
  } catch (e) {
    toasts.error(e instanceof ApiError ? e.message : 'Could not update the reservation.')
  } finally {
    busy.value = null
    await invalidate()
  }
}
</script>

<template>
  <section class="card p-4" data-testid="parts-panel">
    <h2 class="mb-3 font-semibold">Parts</h2>
    <p v-if="!reservations.data.value?.length" class="text-sm text-slate-500">No parts reserved for this repair.</p>
    <ul v-else class="mb-4 divide-y divide-slate-100 text-sm">
      <li v-for="r in reservations.data.value" :key="r.id" class="flex flex-wrap items-center justify-between gap-2 py-2">
        <div>
          <p class="font-medium">{{ r.part_name }} <span class="font-normal text-slate-500">({{ r.sku }})</span></p>
          <p class="text-slate-600">{{ r.quantity }} {{ r.unit }}</p>
        </div>
        <div class="flex items-center gap-2">
          <StatusBadge :status="r.status === 'active' ? 'active_reservation' : (r.status ?? 'active_reservation')" />
          <template v-if="r.status === 'active' && open">
            <AppButton size="sm" :loading="busy === r.id" @click="act(r, 'consume')">Mark used</AppButton>
            <AppButton size="sm" variant="ghost" :disabled="busy === r.id" @click="act(r, 'release')">Release</AppButton>
          </template>
        </div>
      </li>
    </ul>
    <form v-if="open" class="flex flex-col gap-2 sm:flex-row sm:items-end" @submit.prevent="reserve">
      <div class="flex-1">
        <label for="reserve-part" class="field-label">Reserve a part</label>
        <select id="reserve-part" v-model="partId" class="field-input">
          <option value="">Choose a part…</option>
          <option v-for="p in parts.data.value?.results ?? []" :key="p.id" :value="p.id" :disabled="Number(p.quantity_available) <= 0">
            {{ p.name }} ({{ p.sku }}) · {{ p.quantity_available }} available
          </option>
        </select>
      </div>
      <div class="w-24">
        <label for="reserve-qty" class="field-label">Qty</label>
        <input id="reserve-qty" v-model="quantity" class="field-input text-right" inputmode="decimal" />
      </div>
      <AppButton type="submit" variant="secondary" :loading="busy === 'reserve'" :disabled="!partId">Reserve</AppButton>
    </form>
    <FormAlert class="mt-2" :message="error" />
  </section>
</template>
