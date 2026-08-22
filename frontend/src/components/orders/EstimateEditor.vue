<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'
import { computed, reactive, ref } from 'vue'

import { ApiError, api } from '@/api/client'
import { useBusiness, useInvalidateWorkspace, useWorkspaceQueryKey } from '@/api/queries'
import type { Estimate, Paginated, Part } from '@/api/types'
import AppButton from '@/components/ui/AppButton.vue'
import FormAlert from '@/components/ui/FormAlert.vue'
import { useUnsavedChanges } from '@/composables/useUnsavedChanges'
import { money } from '@/lib/format'
import { estimateTotals, type DraftLine } from '@/lib/estimate'

const props = defineProps<{ estimate: Estimate }>()
const emit = defineEmits<{ sent: [] }>()
const invalidate = useInvalidateWorkspace()
const business = useBusiness()

const parts = useQuery({
  queryKey: useWorkspaceQueryKey('parts', { is_active: true, page_size: 100, picker: true }),
  queryFn: () => api.get<Paginated<Part>>('/parts/', { is_active: true, page_size: 100 }),
})
const partById = computed(() => new Map((parts.data.value?.results ?? []).map((p) => [p.id, p])))

const lines = reactive<DraftLine[]>(
  props.estimate.lines.map((l) => ({
    kind: l.kind,
    part: l.part,
    description: l.description,
    quantity: l.quantity,
    unit_price: l.unit_price,
    taxable: l.taxable ?? true,
  })),
)
const notes = ref(props.estimate.notes ?? '')
const errors = ref<Record<string, string[]>>({})
const generalError = ref<string | null>(null)
const saving = ref<'save' | 'send' | null>(null)
const snapshot = ref(JSON.stringify({ lines, notes: notes.value }))
const dirty = computed(() => JSON.stringify({ lines, notes: notes.value }) !== snapshot.value)
useUnsavedChanges(dirty)

const totals = computed(() => estimateTotals(lines, props.estimate.tax_rate))

function add(kind: DraftLine['kind']) {
  lines.push({
    kind,
    part: null,
    description: kind === 'labor' ? 'Labor' : '',
    quantity: '1',
    unit_price: kind === 'labor' ? (business.data.value?.default_labor_rate ?? '0.00') : '0.00',
    taxable: true,
  })
}

function pickPart(line: DraftLine, partId: string) {
  line.part = partId || null
  const part = partById.value.get(partId)
  if (part) {
    line.description = part.name
    line.unit_price = part.selling_price ?? '0.00'
  }
}

function fieldError(index: number, field: string) {
  return errors.value[`lines.${index}.${field}`]?.[0]
}

async function save(): Promise<boolean> {
  errors.value = {}
  generalError.value = null
  try {
    await api.post<Estimate>(`/estimates/${props.estimate.id}/lines/`, {
      notes: notes.value,
      lines: lines.map((l) => ({ ...l, part: l.kind === 'part' ? l.part : null })),
    })
    snapshot.value = JSON.stringify({ lines, notes: notes.value })
    return true
  } catch (error) {
    if (error instanceof ApiError) {
      errors.value = error.fields
      generalError.value = Object.keys(error.fields).length ? 'Some lines need attention.' : error.message
    } else generalError.value = 'Could not save the estimate.'
    return false
  }
}

async function onSave() {
  saving.value = 'save'
  try {
    if (await save()) await invalidate()
  } finally {
    saving.value = null
  }
}

async function onSend() {
  saving.value = 'send'
  try {
    if (!(await save())) return
    await api.post(`/estimates/${props.estimate.id}/send/`)
    await invalidate()
    emit('sent')
  } catch (error) {
    generalError.value = error instanceof ApiError ? error.message : 'Could not send the estimate.'
  } finally {
    saving.value = null
  }
}
</script>

<template>
  <div class="space-y-3" data-testid="estimate-editor">
    <FormAlert :message="generalError" />
    <div v-for="(line, index) in lines" :key="index" class="rounded-md border border-slate-200 p-3">
      <div class="flex flex-wrap items-start gap-2">
        <span class="mt-2 w-14 text-xs font-medium text-slate-500 uppercase">{{ line.kind }}</span>
        <div class="min-w-48 flex-1">
          <select
            v-if="line.kind === 'part'"
            :value="line.part ?? ''"
            class="field-input mb-2"
            :aria-label="`Part for line ${index + 1}`"
            :aria-invalid="fieldError(index, 'part') ? 'true' : undefined"
            @change="pickPart(line, ($event.target as HTMLSelectElement).value)"
          >
            <option value="">Choose a part…</option>
            <option v-for="p in parts.data.value?.results ?? []" :key="p.id" :value="p.id">{{ p.name }} ({{ p.sku }}) · {{ p.quantity_available }} available</option>
          </select>
          <input v-model="line.description" class="field-input" :aria-label="`Description for line ${index + 1}`" placeholder="Description" :aria-invalid="fieldError(index, 'description') ? 'true' : undefined" />
          <p v-if="fieldError(index, 'part') || fieldError(index, 'description')" class="mt-1 text-xs text-red-700">{{ fieldError(index, 'part') || fieldError(index, 'description') }}</p>
        </div>
        <div class="w-20">
          <input v-model="line.quantity" class="field-input text-right" inputmode="decimal" :aria-label="`Quantity for line ${index + 1}`" :aria-invalid="fieldError(index, 'quantity') ? 'true' : undefined" />
          <p v-if="fieldError(index, 'quantity')" class="mt-1 text-xs text-red-700">{{ fieldError(index, 'quantity') }}</p>
        </div>
        <div class="w-28">
          <input v-model="line.unit_price" class="field-input text-right" inputmode="decimal" :aria-label="`Unit price for line ${index + 1}`" :aria-invalid="fieldError(index, 'unit_price') ? 'true' : undefined" />
          <p v-if="fieldError(index, 'unit_price')" class="mt-1 text-xs text-red-700">{{ fieldError(index, 'unit_price') }}</p>
        </div>
        <label class="mt-2 flex items-center gap-1 text-xs text-slate-600"><input v-model="line.taxable" type="checkbox" /> Tax</label>
        <button type="button" class="mt-1.5 rounded p-1 text-slate-500 hover:bg-slate-100 hover:text-red-700" :aria-label="`Remove line ${index + 1}`" @click="lines.splice(index, 1)">✕</button>
      </div>
    </div>
    <p v-if="!lines.length" class="text-sm text-slate-500">Add labour, parts or fees.</p>
    <div class="flex flex-wrap gap-2">
      <AppButton size="sm" variant="secondary" @click="add('labor')">+ Labor</AppButton>
      <AppButton size="sm" variant="secondary" @click="add('part')">+ Part</AppButton>
      <AppButton size="sm" variant="secondary" @click="add('fee')">+ Fee</AppButton>
    </div>
    <div>
      <label for="estimate-notes" class="field-label">Message to the customer</label>
      <textarea id="estimate-notes" v-model="notes" rows="2" class="field-input" />
    </div>
    <dl class="ml-auto w-full max-w-xs space-y-1 text-sm">
      <div class="flex justify-between"><dt>Subtotal</dt><dd class="tabular-nums">{{ money(totals.subtotal, estimate.currency) }}</dd></div>
      <div class="flex justify-between"><dt>Tax ({{ estimate.tax_rate }}%)</dt><dd class="tabular-nums">{{ money(totals.tax, estimate.currency) }}</dd></div>
      <div class="flex justify-between font-semibold"><dt>Total</dt><dd class="tabular-nums" data-testid="estimate-total">{{ money(totals.total, estimate.currency) }}</dd></div>
    </dl>
    <div class="flex flex-wrap justify-end gap-2">
      <AppButton variant="secondary" :loading="saving === 'save'" :disabled="!!saving" @click="onSave">Save draft</AppButton>
      <AppButton :loading="saving === 'send'" :disabled="!!saving || !lines.length" @click="onSend">Send to customer</AppButton>
    </div>
  </div>
</template>
