<script setup lang="ts">
import { watch } from 'vue'

import { api } from '@/api/client'
import { useInvalidateWorkspace } from '@/api/queries'
import type { Part } from '@/api/types'
import AppButton from '@/components/ui/AppButton.vue'
import AppModal from '@/components/ui/AppModal.vue'
import CheckboxField from '@/components/ui/CheckboxField.vue'
import FormAlert from '@/components/ui/FormAlert.vue'
import SelectField from '@/components/ui/SelectField.vue'
import TextField from '@/components/ui/TextField.vue'
import { useApiForm } from '@/composables/useApiForm'
import { useToastStore } from '@/stores/toasts'

const props = defineProps<{ open: boolean; part?: Part | null }>()
const emit = defineEmits<{ close: []; saved: [part: Part] }>()
const invalidate = useInvalidateWorkspace()
const toasts = useToastStore()

const empty = {
  sku: '',
  name: '',
  description: '',
  unit: 'piece',
  purchase_cost: '0.00',
  selling_price: '0.00',
  low_stock_threshold: '0',
  is_active: true,
  initial_quantity: '0',
}
const form = useApiForm({ ...empty })

watch(
  () => props.open,
  (open) => {
    if (!open) return
    const p = props.part
    form.reset(
      p
        ? {
            sku: p.sku,
            name: p.name,
            description: p.description ?? '',
            unit: p.unit ?? 'piece',
            purchase_cost: p.purchase_cost ?? '0.00',
            selling_price: p.selling_price ?? '0.00',
            low_stock_threshold: p.low_stock_threshold ?? '0',
            is_active: p.is_active ?? true,
            initial_quantity: '0',
          }
        : { ...empty },
    )
  },
  { immediate: true },
)

async function onSubmit() {
  const part = await form.submit((v) => {
    if (props.part) {
      const { initial_quantity: _ignored, ...rest } = v
      return api.patch<Part>(`/parts/${props.part.id}/`, rest)
    }
    return api.post<Part>('/parts/', v)
  })
  if (!part) return
  await invalidate()
  toasts.success(props.part ? 'Part updated' : 'Part added')
  emit('saved', part)
}

const units = ['piece', 'set', 'meter', 'ml', 'gram'].map((u) => ({ value: u, label: u }))
</script>

<template>
  <AppModal :open="open" :title="part ? 'Edit part' : 'New part'" @close="emit('close')">
    <form id="part-form" class="space-y-4" novalidate @submit.prevent="onSubmit">
      <FormAlert :message="form.generalError.value" />
      <div class="grid gap-3 sm:grid-cols-3">
        <TextField v-model="form.values.sku" label="SKU" required :error="form.fieldError('sku')" />
        <TextField v-model="form.values.name" class="sm:col-span-2" label="Name" required :error="form.fieldError('name')" />
      </div>
      <TextField v-model="form.values.description" label="Description" :error="form.fieldError('description')" />
      <div class="grid gap-3 sm:grid-cols-3">
        <SelectField v-model="form.values.unit" label="Unit" :options="units" />
        <TextField v-model="form.values.purchase_cost" label="Cost" inputmode="decimal" :error="form.fieldError('purchase_cost')" />
        <TextField v-model="form.values.selling_price" label="Price" inputmode="decimal" :error="form.fieldError('selling_price')" />
        <TextField v-model="form.values.low_stock_threshold" label="Low-stock alert at" inputmode="decimal" :error="form.fieldError('low_stock_threshold')" />
        <TextField v-if="!part" v-model="form.values.initial_quantity" label="Opening stock" inputmode="decimal" :error="form.fieldError('initial_quantity')" />
      </div>
      <CheckboxField v-if="part" v-model="form.values.is_active" label="Active (available for new estimates and reservations)" />
      <p v-if="part" class="text-xs text-slate-500">Stock levels change only through receiving, adjustments and repairs, so every change is in the stock history.</p>
    </form>
    <template #footer>
      <AppButton variant="secondary" @click="emit('close')">Cancel</AppButton>
      <AppButton type="submit" form="part-form" :loading="form.submitting.value">Save</AppButton>
    </template>
  </AppModal>
</template>
