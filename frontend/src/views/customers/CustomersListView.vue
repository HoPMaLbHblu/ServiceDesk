<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import type { Customer } from '@/api/types'
import CustomerFormModal from '@/components/customers/CustomerFormModal.vue'
import AppButton from '@/components/ui/AppButton.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import ErrorState from '@/components/ui/ErrorState.vue'
import LoadingState from '@/components/ui/LoadingState.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import PaginationBar from '@/components/ui/PaginationBar.vue'
import SearchInput from '@/components/ui/SearchInput.vue'
import { useListQuery } from '@/composables/useListQuery'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()
const router = useRouter()
const { search, page, filters, query } = useListQuery<Customer>('customers', '/customers/', ['is_archived'])
const creating = ref(false)

function onCreated(customer: Customer) {
  creating.value = false
  void router.push({ name: 'customer', params: { id: customer.id } })
}
</script>

<template>
  <div>
    <PageHeader title="Customers" :subtitle="session.isTechnician ? 'Customers of the repairs assigned to you.' : undefined">
      <template v-if="session.isManager" #actions>
        <AppButton @click="creating = true">New customer</AppButton>
      </template>
    </PageHeader>

    <div class="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center">
      <SearchInput v-model="search" label="Search customers" placeholder="Name, phone, email, serial…" />
      <label class="flex items-center gap-2 text-sm text-slate-700">
        <input v-model="filters.is_archived" type="checkbox" true-value="true" false-value="" class="h-4 w-4 rounded border-slate-300" />
        Show archived only
      </label>
    </div>

    <div class="card overflow-hidden">
      <LoadingState v-if="query.isPending.value" />
      <ErrorState v-else-if="query.isError.value" class="m-4" :error="query.error.value" :retry="query.refetch" />
      <EmptyState v-else-if="!query.data.value?.results.length" :title="search ? 'No customers match your search' : 'No customers yet'">
        <AppButton v-if="session.isManager && !search" @click="creating = true">Add your first customer</AppButton>
      </EmptyState>
      <template v-else>
        <div class="overflow-x-auto">
          <table class="table-base">
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col" class="hidden sm:table-cell">Phone</th>
                <th scope="col" class="hidden md:table-cell">Email</th>
                <th scope="col" class="text-right">Devices</th>
                <th scope="col" class="text-right">Open orders</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100 bg-white">
              <tr v-for="c in query.data.value.results" :key="c.id" class="hover:bg-slate-50">
                <td>
                  <RouterLink :to="{ name: 'customer', params: { id: c.id } }" class="font-medium text-brand-700 hover:underline">{{ c.full_name }}</RouterLink>
                  <p v-if="c.company" class="text-xs text-slate-500">{{ c.company }}</p>
                  <p class="text-xs text-slate-500 sm:hidden">{{ c.phone }}</p>
                </td>
                <td class="hidden sm:table-cell">{{ c.phone || '—' }}</td>
                <td class="hidden md:table-cell">{{ c.email || '—' }}</td>
                <td class="text-right tabular-nums">{{ c.device_count }}</td>
                <td class="text-right tabular-nums">{{ c.open_order_count }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <PaginationBar v-model:page="page" :total-pages="query.data.value.total_pages" :count="query.data.value.count" />
      </template>
    </div>

    <CustomerFormModal :open="creating" @close="creating = false" @saved="onCreated" />
  </div>
</template>
