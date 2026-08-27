import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { queryClient } from '@/lib/queryClient'
import { mockFetch, sessionFor } from '@/test/fetch'

import { useSessionStore } from './session'

beforeEach(() => {
  setActivePinia(createPinia())
  queryClient.clear()
  localStorage.clear()
})

describe('session store', () => {
  it('drops every cached record when the workspace changes', async () => {
    const session = useSessionStore()
    session.apply(sessionFor('owner'))
    queryClient.setQueryData(['ws', 'ws-a', 'customers'], [{ id: 'c1', full_name: 'Alpha customer' }])

    mockFetch({ 'POST /api/v1/workspaces/switch/': () => ({ body: sessionFor('technician', { id: 'ws-b', name: 'Beta Fixers' }) }) })
    await session.switchWorkspace('ws-b')

    expect(session.workspaceId).toBe('ws-b')
    expect(session.role).toBe('technician')
    expect(queryClient.getQueryCache().getAll()).toHaveLength(0)
  })

  it('keeps the cache when the same session is re-applied', () => {
    const session = useSessionStore()
    session.apply(sessionFor('owner'))
    queryClient.setQueryData(['ws', 'ws-a', 'orders'], [])
    session.apply(sessionFor('owner'))
    expect(queryClient.getQueryData(['ws', 'ws-a', 'orders'])).toEqual([])
  })

  it('marks the session expired and forgets the user and data on a 401', () => {
    const session = useSessionStore()
    session.apply(sessionFor('manager'))
    queryClient.setQueryData(['ws', 'ws-a', 'orders'], [{ id: 'o1' }])
    session.markExpired()
    expect(session.isAuthenticated).toBe(false)
    expect(session.expired).toBe(true)
    expect(session.workspace).toBeNull()
    expect(queryClient.getQueryCache().getAll()).toHaveLength(0)
  })

  it('clears everything on logout even if the request fails', async () => {
    const session = useSessionStore()
    session.apply(sessionFor('owner'))
    queryClient.setQueryData(['ws', 'ws-a', 'orders'], [])
    mockFetch({
      'POST /api/v1/auth/logout/': () => ({ status: 500, body: {} }),
      'GET /api/v1/auth/session/': () => ({ body: sessionFor(null) && { ...sessionFor(null), authenticated: false, user: null } }),
    })
    await expect(session.logout()).rejects.toBeTruthy()
    expect(session.isAuthenticated).toBe(false)
    expect(queryClient.getQueryCache().getAll()).toHaveLength(0)
  })

  it('reopens the workspace used last on this browser after sign-in', async () => {
    const session = useSessionStore()
    session.apply(sessionFor('owner', { id: 'ws-b', name: 'Beta Fixers' }))
    session.apply({ ...sessionFor(null), authenticated: false, user: null })
    const noWorkspace = { ...sessionFor('owner'), active_workspace: null }
    const { calls } = mockFetch({
      'POST /api/v1/auth/login/': () => ({ body: noWorkspace }),
      'POST /api/v1/workspaces/switch/': () => ({ body: sessionFor('technician', { id: 'ws-b', name: 'Beta Fixers' }) }),
    })
    await session.login('sam@example.com', 'secret')
    expect(calls.map((c) => c.url)).toEqual(['/api/v1/auth/login/', '/api/v1/workspaces/switch/'])
    expect(calls[1]!.json).toEqual({ business_id: 'ws-b' })
    expect(session.workspaceId).toBe('ws-b')
  })
})
