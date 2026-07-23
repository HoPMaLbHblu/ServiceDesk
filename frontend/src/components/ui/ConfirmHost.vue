<script setup lang="ts">
import { useConfirmStore } from '@/composables/useConfirm'

import AppButton from './AppButton.vue'
import AppModal from './AppModal.vue'

const confirm = useConfirmStore()
</script>

<template>
  <AppModal :open="!!confirm.current" :title="confirm.current?.title ?? ''" @close="confirm.answer(false)">
    <p class="text-sm text-slate-700">{{ confirm.current?.message }}</p>
    <template #footer>
      <AppButton variant="secondary" @click="confirm.answer(false)">Cancel</AppButton>
      <AppButton :variant="confirm.current?.danger ? 'danger' : 'primary'" @click="confirm.answer(true)">
        {{ confirm.current?.confirmLabel ?? 'Confirm' }}
      </AppButton>
    </template>
  </AppModal>
</template>
