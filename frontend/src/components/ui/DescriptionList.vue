<script setup lang="ts">
defineProps<{ items: { label: string; value: string | number | null | undefined }[] }>()
</script>

<template>
  <dl class="grid grid-cols-1 gap-x-4 gap-y-3 text-sm sm:grid-cols-2">
    <div v-for="item in items" :key="item.label">
      <dt class="text-xs font-medium text-slate-500 uppercase">{{ item.label }}</dt>
      <dd class="mt-0.5 break-words text-slate-900">{{ item.value === null || item.value === undefined || item.value === '' ? '—' : item.value }}</dd>
    </div>
  </dl>
</template>
