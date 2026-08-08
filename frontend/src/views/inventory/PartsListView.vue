<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import type { Part } from '@/api/types'
import PartFormModal from '@/components/inventory/PartFormModal.vue'
import AppBadge from '@/components/ui/AppBadge.vue'
import AppButton from '@/components/ui/AppButton.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import ErrorState from '@/components/ui/ErrorState.vue'
import LoadingState from '@/components/ui/LoadingState.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import PaginationBar from '@/components/ui/PaginationBar.vue'
import SearchInput from '@/components/ui/SearchInput.vue'
import { useListQuery } from '@/composables/useListQuery'
import { money } from '@/lib/format'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()
const router = useRouter()
const { search, page, filters, query } = useListQuery<Part>('parts', '/parts/', ['low_stock', 'is_active'])
const creating = ref(false)
</script>

<template>
  <div>
    <PageHeader title="Inventory">
      <template v-if="session.isManager" #actions>
        <AppButton @click="creating = true">New part</AppButton>
      </template>
    </PageHeader>
    <div class="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center">
      <SearchInput v-model="search" label="Search parts" placeholder="SKU or name" />
      <label class="flex items-center gap-2 text-sm">
        <input v-model="filters.low_stock" type="checkbox" true-value="true" false-value="" class="h-4 w-4" /> Low stock only
      </label>
    </div>
    <div class="card overflow-hidden">
      <LoadingState v-if="query.isPending.value" />
      <ErrorState v-else-if="query.isError.value" class="m-4" :error="query.error.value" :retry="query.refetch" />
      <EmptyState v-else-if="!query.data.value?.results.length" title="No parts found" />
      <template v-else>
        <div class="overflow-x-auto">
          <table class="table-base">
            <thead>
              <tr>
                <th scope="col">Part</th>
                <th scope="col" class="text-right">On hand</th>
                <th scope="col" class="text-right">Reserved</th>
                <th scope="col" class="text-right">Available</th>
                <th scope="col" class="hidden text-right sm:table-cell">Price</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100 bg-white">
              <tr v-for="p in query.data.value.results" :key="p.id" class="cursor-pointer hover:bg-slate-50" @click="router.push({ name: 'part', params: { id: p.id } })">
                <td>
                  <RouterLink :to="{ name: 'part', params: { id: p.id } }" class="font-medium text-brand-700 hover:underline" @click.stop>{{ p.name }}</RouterLink>
                  <p class="text-xs text-slate-500">
                    {{ p.sku }}
                    <AppBadge v-if="p.is_low_stock" tone="amber" class="ml-1">Low</AppBadge>
                    <AppBadge v-if="!p.is_active" class="ml-1">Inactive</AppBadge>
                  </p>
                </td>
                <td class="text-right tabular-nums">{{ p.quantity_on_hand }}</td>
                <td class="text-right tabular-nums">{{ p.quantity_reserved }}</td>
                <td :class="['text-right font-medium tabular-nums', p.is_low_stock ? 'text-amber-800' : '']">{{ p.quantity_available }}</td>
                <td class="hidden text-right tabular-nums sm:table-cell">{{ money(p.selling_price, session.workspace?.currency) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <PaginationBar v-model:page="page" :total-pages="query.data.value.total_pages" :count="query.data.value.count" />
      </template>
    </div>
    <PartFormModal :open="creating" @close="creating = false" @saved="(p) => { creating = false; router.push({ name: 'part', params: { id: p.id } }) }" />
  </div>
</template>
