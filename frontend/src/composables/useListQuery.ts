import { keepPreviousData, useQuery } from '@tanstack/vue-query'
import { computed, ref, watch, type Ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api } from '@/api/client'
import { useWorkspaceQueryKey } from '@/api/queries'
import type { Paginated } from '@/api/types'

import { useDebounced } from './useDebounced'

/**
 * A paginated, searchable list whose search text, filters and page live in the
 * URL, so the back button and shared links restore the same view.
 */
export function useListQuery<T>(resource: string, path: string, filterNames: string[] = []) {
  const route = useRoute()
  const router = useRouter()
  const q = (name: string) => (typeof route.query[name] === 'string' ? (route.query[name] as string) : '')

  const search = ref(q('search'))
  const page = ref(Number(q('page')) || 1)
  const filters = ref<Record<string, string>>(Object.fromEntries(filterNames.map((n) => [n, q(n)])))
  const debounced = useDebounced(search, 300)

  watch([debounced, filters], () => (page.value = 1), { deep: true })
  watch(
    [debounced, page, filters],
    () => {
      const query: Record<string, string> = {}
      if (debounced.value) query.search = debounced.value
      if (page.value > 1) query.page = String(page.value)
      for (const [k, v] of Object.entries(filters.value)) if (v) query[k] = v
      void router.replace({ query })
    },
    { deep: true },
  )

  const params = computed(() => ({ search: debounced.value, page: page.value, ...filters.value }))
  const query = useQuery({
    queryKey: useWorkspaceQueryKey(resource, params),
    queryFn: ({ signal }) => api.get<Paginated<T>>(path, params.value, signal),
    placeholderData: keepPreviousData,
  })

  return { search, page, filters: filters as Ref<Record<string, string>>, query }
}
