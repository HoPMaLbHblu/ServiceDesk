<script setup lang="ts">
import { watch } from 'vue'

import { api } from '@/api/client'
import { useInvalidateWorkspace } from '@/api/queries'
import type { Device } from '@/api/types'
import AppButton from '@/components/ui/AppButton.vue'
import AppModal from '@/components/ui/AppModal.vue'
import FormAlert from '@/components/ui/FormAlert.vue'
import SelectField from '@/components/ui/SelectField.vue'
import TextField from '@/components/ui/TextField.vue'
import { useApiForm } from '@/composables/useApiForm'
import { DEVICE_KINDS } from '@/lib/format'
import { useToastStore } from '@/stores/toasts'

const props = defineProps<{ open: boolean; customerId: string; device?: Device | null }>()
const emit = defineEmits<{ close: []; saved: [device: Device] }>()
const invalidate = useInvalidateWorkspace()
const toasts = useToastStore()

const empty = { kind: 'phone', brand: '', model: '', serial_number: '', imei: '', color: '', notes: '' }
const form = useApiForm({ ...empty })

watch(
  () => props.open,
  (open) => {
    if (!open) return
    const d = props.device
    form.reset(
      d
        ? { kind: d.kind ?? 'other', brand: d.brand, model: d.model, serial_number: d.serial_number ?? '', imei: d.imei ?? '', color: d.color ?? '', notes: d.notes ?? '' }
        : { ...empty },
    )
  },
  { immediate: true },
)

async function onSubmit() {
  const device = await form.submit((values) =>
    props.device
      ? api.patch<Device>(`/devices/${props.device.id}/`, values)
      : api.post<Device>('/devices/', { ...values, customer: props.customerId }),
  )
  if (!device) return
  await invalidate()
  toasts.success(props.device ? 'Device updated' : 'Device added')
  emit('saved', device)
}
</script>

<template>
  <AppModal :open="open" :title="device ? 'Edit device' : 'Add device'" @close="emit('close')">
    <form id="device-form" class="space-y-4" novalidate @submit.prevent="onSubmit">
      <FormAlert :message="form.generalError.value" />
      <SelectField v-model="form.values.kind" label="Type" :options="DEVICE_KINDS" :error="form.fieldError('kind')" />
      <div class="grid gap-3 sm:grid-cols-2">
        <TextField v-model="form.values.brand" label="Brand" required :error="form.fieldError('brand')" />
        <TextField v-model="form.values.model" label="Model" required :error="form.fieldError('model')" />
        <TextField v-model="form.values.serial_number" label="Serial number" :error="form.fieldError('serial_number')" />
        <TextField v-model="form.values.imei" label="IMEI" :error="form.fieldError('imei')" />
        <TextField v-model="form.values.color" label="Colour" :error="form.fieldError('color')" />
      </div>
      <TextField v-model="form.values.notes" label="Condition notes" :error="form.fieldError('notes')" />
    </form>
    <template #footer>
      <AppButton variant="secondary" @click="emit('close')">Cancel</AppButton>
      <AppButton type="submit" form="device-form" :loading="form.submitting.value">Save</AppButton>
    </template>
  </AppModal>
</template>
