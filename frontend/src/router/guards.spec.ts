import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { useSessionStore } from '@/stores/session'
import { sessionFor } from '@/test/fetch'

import { createAppRouter } from './index'

let router = createAppRouter()

async function visit(path: string) {
  await router.push(path).catch(() => undefined)
  return router.currentRoute.value
}

beforeEach(async () => {
  setActivePinia(createPinia())
  useSessionStore().restored = true
  router = createAppRouter()
  await router.replace('/forgot-password').catch(() => undefined)
})

describe('route guards', () => {
  it('sends signed-out visitors to sign in and remembers where they were going', async () => {
    const route = await visit('/orders/abc')
    expect(route.name).toBe('login')
    expect(route.query.next).toBe('/orders/abc')
  })

  it('keeps public pages public', async () => {
    expect((await visit('/approve/some-token')).name).toBe('public-approval')
  })

  it.each([
    ['technician', '/invoices', 'forbidden'],
    ['technician', '/reports', 'forbidden'],
    ['technician', '/settings/team', 'forbidden'],
    ['technician', '/orders', 'orders'],
    ['manager', '/invoices', 'invoices'],
    ['manager', '/reports', 'forbidden'],
    ['manager', '/settings/business', 'forbidden'],
    ['owner', '/reports', 'reports'],
    ['owner', '/settings/audit', 'settings-audit'],
  ] as const)('%s opening %s lands on %s', async (role, path, expected) => {
    useSessionStore().apply(sessionFor(role))
    expect((await visit(path)).name).toBe(expected)
  })

  it('sends a signed-in user without a workspace to onboarding', async () => {
    useSessionStore().apply(sessionFor(null))
    expect((await visit('/orders')).name).toBe('welcome')
  })

  it('redirects signed-in users away from the login page', async () => {
    useSessionStore().apply(sessionFor('owner'))
    expect((await visit('/login')).name).toBe('dashboard')
  })
})
