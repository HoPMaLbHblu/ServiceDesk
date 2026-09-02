import { afterEach, describe, expect, it } from 'vitest'

import { queryClient } from '@/lib/queryClient'
import { mockFetch, sessionFor } from '@/test/fetch'
import { flush, mountAs } from '@/test/mount'

import WorkspaceSwitcher from './WorkspaceSwitcher.vue'

afterEach(() => document.body.replaceChildren())

describe('WorkspaceSwitcher', () => {
  it('switches through the server and drops the previous workspace data', async () => {
    const { wrapper, session } = await mountAs('owner', WorkspaceSwitcher, {}, '/orders')
    queryClient.setQueryData(['ws', 'ws-a', 'customers'], [{ id: 'secret-alpha-customer' }])
    const { calls } = mockFetch({
      'POST /api/v1/workspaces/switch/': () => ({ body: sessionFor('technician', { id: 'ws-b', name: 'Beta Fixers' }) }),
    })

    await wrapper.get('select').setValue('ws-b')
    await flush()

    expect(calls[0]).toMatchObject({ method: 'POST', json: { business_id: 'ws-b' } })
    expect(session.workspace?.name).toBe('Beta Fixers')
    expect(session.role).toBe('technician')
    expect(queryClient.getQueryData(['ws', 'ws-a', 'customers'])).toBeUndefined()
  })

  it('stays on the current workspace when the server refuses', async () => {
    const { wrapper, session } = await mountAs('owner', WorkspaceSwitcher)
    mockFetch({
      'POST /api/v1/workspaces/switch/': () => ({ status: 400, body: { error: { code: 'workspace_not_found', message: 'You are not a member of that workspace.' } } }),
    })
    await wrapper.get('select').setValue('ws-b')
    await flush()
    expect(session.workspaceId).toBe('ws-a')
  })
})
