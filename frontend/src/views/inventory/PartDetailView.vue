<script setup lang="ts">
import { keepPreviousData, useQuery } from '@tanstack/vue-query'
import { computed, ref } from 'vue'

import { api } from '@/api/client'
import { useInvalidateWorkspace, useWorkspaceQueryKey } from '@/api/queries'
import type { Paginated, Part, StockMovement } from '@/api/types'
import PartFormModal from '@/components/inventory/PartFormModal.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppModal from '@/components/ui/AppModal.vue'
import ErrorState from '@/components/ui/ErrorState.vue'
import FormAlert from '@/components/ui/FormAlert.vue'
import LoadingState from '@/components/ui/LoadingState.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import PaginationBar from '@/components/ui/PaginationBar.vue'
import TextField from '@/components/ui/TextField.vue'
import { useApiForm } from '@/composables/useApiForm'
import { dateTime, label, money } from '@/lib/format'
import { useSessionStore } from '@/stores/session'
import { useToastStore } from '@/stores/toasts'

const props = defineProps<{ id: string }>()
const session = useSessionStore()
const toasts = useToastStore()
const invalidate = useInvalidateWorkspace()
const page = ref(1)

const part = useQuery({
  queryKey: useWorkspaceQueryKey('part', props.id),
  queryFn: () => api.get<Part>(`/parts/${props.id}/`),
})
const movements = useQuery({
  queryKey: useWorkspaceQueryKey('part', props.id, 'movements', page),
  queryFn: () => api.get<Paginated<StockMovement>>(`/parts/${props.id}/movements/`, { page: page.value }),
  placeholderData: keepPreviousData,
})

const editing = ref(false)
const dialog = ref<'receive' | 'adjust' | null>(null)
const receive = useApiForm({ quantity: '', unit_cost: '', reason: '' })
const adjust = useApiForm({ counted_quantity: '', reason: '' })

function openDialog(kind: 'receive' | 'adjust') {
  receive.reset({ quantity: '', unit_cost: part.data.value?.purchase_cost ?? '', reason: '' })
  adjust.reset({ counted_quantity: part.data.value?.quantity_on_hand ?? '', reason: '' })
  dialog.value = kind
}

async function submit() {
  const ok =
    dialog.value === 'receive'
      ? await receive.submit((v) => api.post(`/parts/${props.id}/receive/`, { ...v, unit_cost: v.unit_cost || undefined }))
      : await adjust.submit((v) => api.post(`/parts/${props.id}/adjust/`, v))
  if (!ok) return
  toasts.success(dialog.value === 'receive' ? 'Stock received' : 'Stock count saved')
  dialog.value = null
  await invalidate()
}

const form = computed(() => (dialog.value === 'receive' ? receive : adjust))
const signed = (v: string | undefined) => (v && !v.startsWith('-') && Number(v) !== 0 ? `+${v}` : (v ?? ''))
</script>

<template>
  <div>
    <LoadingState v-if="part.isPending.value" />
    <ErrorState v-else-if="part.isError.value" :error="part.error.value" />
    <template v-else-if="part.data.value">
      <PageHeader :title="part.data.value.name" :subtitle="`${part.data.value.sku}${part.data.value.description ? ' · ' + part.data.value.description : ''}`">
        <template #breadcrumb><RouterLink :to="{ name: 'inventory' }" class="text-sm text-slate-500 hover:underline">← Inventory</RouterLink></template>
        <template v-if="session.isManager" #actions>
          <AppButton @click="openDialog('receive')">Receive stock</AppButton>
          <AppButton variant="secondary" @click="openDialog('adjust')">Stock count</AppButton>
          <AppButton variant="ghost" @click="editing = true">Edit</AppButton>
        </template>
      </PageHeader>

      <div class="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div class="card p-3"><p class="text-xs text-slate-500">On hand</p><p class="text-xl font-semibold tabular-nums">{{ part.data.value.quantity_on_hand }}</p></div>
        <div class="card p-3"><p class="text-xs text-slate-500">Reserved for repairs</p><p class="text-xl font-semibold tabular-nums">{{ part.data.value.quantity_reserved }}</p></div>
        <div class="card p-3">
          <p class="text-xs text-slate-500">Available</p>
          <p :class="['text-xl font-semibold tabular-nums', part.data.value.is_low_stock ? 'text-amber-800' : '']">{{ part.data.value.quantity_available }}</p>
          <p class="text-xs text-slate-500">alert at {{ part.data.value.low_stock_threshold }}</p>
        </div>
        <div class="card p-3">
          <p class="text-xs text-slate-500">Price · cost</p>
          <p class="text-xl font-semibold">{{ money(part.data.value.selling_price, session.workspace?.currency) }}</p>
          <p class="text-xs text-slate-500">cost {{ money(part.data.value.purchase_cost, session.workspace?.currency) }}</p>
        </div>
      </div>

      <section v-if="session.isManager" class="card overflow-hidden">
        <h2 class="border-b border-slate-200 px-4 py-3 font-semibold">Stock history</h2>
        <div class="overflow-x-auto">
          <table class="table-base">
            <thead>
              <tr>
                <th scope="col">When</th>
                <th scope="col">Movement</th>
                <th scope="col" class="text-right">On hand</th>
                <th scope="col" class="text-right">Reserved</th>
                <th scope="col">By</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
              <tr v-for="m in movements.data.value?.results ?? []" :key="m.id">
                <td class="whitespace-nowrap">{{ dateTime(m.created_at) }}</td>
                <td>
                  {{ label(m.kind) }}
                  <RouterLink v-if="m.order_reference" :to="{ name: 'orders', query: { search: m.order_reference } }" class="text-brand-700 hover:underline">{{ m.order_reference }}</RouterLink>
                  <p v-if="m.reason" class="text-xs text-slate-500">{{ m.reason }}</p>
                </td>
                <td class="text-right whitespace-nowrap tabular-nums">{{ signed(m.on_hand_delta) }} → {{ m.on_hand_after }}</td>
                <td class="text-right whitespace-nowrap tabular-nums">{{ signed(m.reserved_delta) }} → {{ m.reserved_after }}</td>
                <td>{{ m.actor_name }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <PaginationBar v-if="movements.data.value" v-model:page="page" :total-pages="movements.data.value.total_pages" :count="movements.data.value.count" />
      </section>

      <PartFormModal :open="editing" :part="part.data.value" @close="editing = false" @saved="editing = false" />
      <AppModal :open="!!dialog" :title="dialog === 'receive' ? 'Receive stock' : 'Record a stock count'" @close="dialog = null">
        <form id="stock-form" class="space-y-3" novalidate @submit.prevent="submit">
          <FormAlert :message="form.generalError.value" />
          <template v-if="dialog === 'receive'">
            <TextField v-model="receive.values.quantity" label="Quantity received" inputmode="decimal" required :error="receive.fieldError('quantity')" />
            <TextField v-model="receive.values.unit_cost" label="Unit cost" inputmode="decimal" :error="receive.fieldError('unit_cost')" />
            <TextField v-model="receive.values.reason" label="Supplier or reference" :error="receive.fieldError('reason')" />
          </template>
          <template v-else>
            <p class="text-sm text-slate-600">Enter what is physically on the shelf. The difference is recorded as an adjustment.</p>
            <TextField v-model="adjust.values.counted_quantity" label="Counted quantity" inputmode="decimal" required :error="adjust.fieldError('counted_quantity')" />
            <TextField v-model="adjust.values.reason" label="Reason" required :error="adjust.fieldError('reason')" />
          </template>
        </form>
        <template #footer>
          <AppButton variant="secondary" @click="dialog = null">Cancel</AppButton>
          <AppButton type="submit" form="stock-form" :loading="form.submitting.value">Save</AppButton>
        </template>
      </AppModal>
    </template>
  </div>
</template>
