<script setup lang="ts">
import { ref } from 'vue'

import { ApiError, api } from '@/api/client'
import { useInvalidateWorkspace, useStaffOptions } from '@/api/queries'
import type { OrderDetail } from '@/api/types'
import AppButton from '@/components/ui/AppButton.vue'
import DescriptionList from '@/components/ui/DescriptionList.vue'
import FormAlert from '@/components/ui/FormAlert.vue'
import SelectField from '@/components/ui/SelectField.vue'
import TextAreaField from '@/components/ui/TextAreaField.vue'
import TextField from '@/components/ui/TextField.vue'
import { useApiForm } from '@/composables/useApiForm'
import { PRIORITIES, date, dateTime, label } from '@/lib/format'
import { useSessionStore } from '@/stores/session'

const props = defineProps<{ order: OrderDetail }>()
const session = useSessionStore()
const staff = useStaffOptions()
const invalidate = useInvalidateWorkspace()
const editing = ref(false)
const conflict = ref(false)

const form = useApiForm({ problem_description: '', priority: 'normal', assigned_technician: '', expected_completion_date: '' })

function startEdit() {
  const o = props.order
  conflict.value = false
  form.reset({
    problem_description: o.problem_description,
    priority: o.priority ?? 'normal',
    assigned_technician: o.assigned_technician?.id ?? '',
    expected_completion_date: o.expected_completion_date ?? '',
  })
  editing.value = true
}

async function save() {
  conflict.value = false
  const saved = await form.submit(async (values) => {
    try {
      await api.patch(`/orders/${props.order.id}/`, {
        ...values,
        assigned_technician: values.assigned_technician || null,
        expected_completion_date: values.expected_completion_date || null,
        // The server refuses the change if someone else saved in the meantime.
        version: props.order.version,
      })
      return true
    } catch (error) {
      if (error instanceof ApiError && error.code === 'stale_version') {
        conflict.value = true
        return false
      }
      throw error
    }
  })
  if (saved) {
    editing.value = false
    await invalidate()
  }
}

async function reload() {
  await invalidate()
  startEdit()
}
</script>

<template>
  <section class="card p-4">
    <div class="mb-3 flex items-center justify-between">
      <h2 class="font-semibold">Details</h2>
      <AppButton v-if="session.isManager && !editing && order.allowed_transitions.length" size="sm" variant="ghost" @click="startEdit">Edit</AppButton>
    </div>
    <form v-if="editing" class="space-y-3" novalidate @submit.prevent="save">
      <FormAlert v-if="conflict" tone="warning" message="Someone else changed this order while you were editing. Reload to see their changes, then apply yours again." data-testid="conflict">
        <button type="button" class="ml-1 font-medium underline" @click="reload">Reload</button>
      </FormAlert>
      <FormAlert :message="form.generalError.value" />
      <TextAreaField v-model="form.values.problem_description" label="Problem" :rows="3" :error="form.fieldError('problem_description')" />
      <div class="grid gap-3 sm:grid-cols-3">
        <SelectField v-model="form.values.priority" label="Priority" :options="PRIORITIES" />
        <SelectField
          v-model="form.values.assigned_technician"
          label="Technician"
          placeholder=""
          :options="(staff.data.value ?? []).map((s) => ({ value: s.user_id, label: s.full_name }))"
          :error="form.fieldError('assigned_technician')"
        />
        <TextField v-model="form.values.expected_completion_date" label="Promised by" type="date" :error="form.fieldError('expected_completion_date')" />
      </div>
      <div class="flex justify-end gap-2">
        <AppButton variant="secondary" @click="editing = false">Cancel</AppButton>
        <AppButton type="submit" :disabled="conflict">Save</AppButton>
      </div>
    </form>
    <template v-else>
      <p class="mb-4 text-sm whitespace-pre-line">{{ order.problem_description }}</p>
      <DescriptionList
        :items="[
          { label: 'Device', value: order.device_label },
          { label: 'Serial / IMEI', value: [order.device.serial_number, order.device.imei].filter(Boolean).join(' · ') },
          { label: 'Technician', value: order.assigned_technician?.name ?? 'Unassigned' },
          { label: 'Priority', value: label(order.priority ?? 'normal') },
          { label: 'Promised by', value: date(order.expected_completion_date) },
          { label: 'Created', value: dateTime(order.created_at) + (order.source === 'portal' ? ' (portal request)' : '') },
        ]"
      />
      <p v-if="order.cancellation_reason" class="mt-3 text-sm text-red-800">Cancelled: {{ order.cancellation_reason }}</p>
    </template>
  </section>
</template>
