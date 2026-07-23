<script setup lang="ts">
const props = defineProps<{ page: number; totalPages: number; count: number }>()
const emit = defineEmits<{ 'update:page': [page: number] }>()

function go(page: number) {
  if (page >= 1 && page <= props.totalPages) emit('update:page', page)
}
</script>

<template>
  <nav v-if="totalPages > 1" class="flex items-center justify-between border-t border-slate-200 px-3 py-2 text-sm" aria-label="Pagination">
    <span class="text-slate-600">{{ count }} total · page {{ page }} of {{ totalPages }}</span>
    <div class="flex gap-2">
      <button type="button" class="rounded border border-slate-300 bg-white px-2.5 py-1 disabled:opacity-50" :disabled="page <= 1" @click="go(page - 1)">Previous</button>
      <button type="button" class="rounded border border-slate-300 bg-white px-2.5 py-1 disabled:opacity-50" :disabled="page >= totalPages" @click="go(page + 1)">Next</button>
    </div>
  </nav>
</template>
