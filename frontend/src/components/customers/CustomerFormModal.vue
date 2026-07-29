<script setup lang="ts">
import { useMutation } from '@tanstack/vue-query'
import { watch } from 'vue'

import { api } from '@/api/client'
import { useInvalidateWorkspace } from '@/api/queries'
import type { Customer } from '@/api/types'
import AppButton from '@/components/ui/AppButton.vue'
import AppModal from '@/components/ui/AppModal.vue'
import CheckboxField from '@/components/ui/CheckboxField.vue'
import FormAlert from '@/components/ui/FormAlert.vue'
import TextAreaField from '@/components/ui/TextAreaField.vue'
import TextField from '@/components/ui/TextField.vue'
import { useApiForm } from '@/composables/useApiForm'
import { useToastStore } from '@/stores/toasts'

const props = defineProps<{ open: boolean; customer?: Customer | null }>()
const emit = defineEmits<{ close: []; saved: [customer: Customer] }>()
const invalidate = useInvalidateWorkspace()
const toasts = useToastStore()

const empty = { full_name: '', company: '', email: '', phone: '', address: '', customer_notes: '', marketing_opt_in: false }
const form = useApiForm({ ...empty })

watch(
  () => props.open,
  (open) => {
    if (!open) return
    const c = props.customer
    form.reset(
      c
        ? {
            full_name: c.full_name,
            company: c.company ?? '',
            email: c.email ?? '',
            phone: c.phone ?? '',
            address: c.address ?? '',
            customer_notes: c.customer_notes ?? '',
            marketing_opt_in: c.marketing_opt_in ?? false,
          }
        : { ...empty },
    )
  },
  { immediate: true },
)

const save = useMutation({
  mutationFn: (values: typeof empty) =>
    props.customer ? api.patch<Customer>(`/customers/${props.customer.id}/`, values) : api.post<Customer>('/customers/', values),
})

async function onSubmit() {
  const customer = await form.submit((values) => save.mutateAsync(values))
  if (!customer) return
  await invalidate()
  toasts.success(props.customer ? 'Customer updated' : 'Customer added')
  emit('saved', customer)
}
</script>

<template>
  <AppModal :open="open" :title="customer ? 'Edit customer' : 'New customer'" @close="emit('close')">
    <form id="customer-form" class="space-y-4" novalidate @submit.prevent="onSubmit">
      <FormAlert :message="form.generalError.value" />
      <TextField v-model="form.values.full_name" label="Full name" required :error="form.fieldError('full_name')" />
      <div class="grid gap-3 sm:grid-cols-2">
        <TextField v-model="form.values.phone" label="Phone" type="tel" :error="form.fieldError('phone')" />
        <TextField v-model="form.values.email" label="Email" type="email" :error="form.fieldError('email')" />
      </div>
      <TextField v-model="form.values.company" label="Company" :error="form.fieldError('company')" />
      <TextAreaField v-model="form.values.address" label="Address" :rows="2" :error="form.fieldError('address')" />
      <TextAreaField v-model="form.values.customer_notes" label="Notes about this customer" :rows="2" :error="form.fieldError('customer_notes')" />
      <CheckboxField v-model="form.values.marketing_opt_in" label="Agreed to receive marketing emails" />
    </form>
    <template #footer>
      <AppButton variant="secondary" @click="emit('close')">Cancel</AppButton>
      <AppButton type="submit" form="customer-form" :loading="form.submitting.value">Save</AppButton>
    </template>
  </AppModal>
</template>
