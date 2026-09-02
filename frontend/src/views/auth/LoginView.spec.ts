import { afterEach, describe, expect, it, vi } from 'vitest'

import { mockFetch, sessionFor } from '@/test/fetch'
import { flush, mountAs } from '@/test/mount'

import LoginView from './LoginView.vue'

afterEach(() => document.body.replaceChildren())

describe('LoginView', () => {
  it('shows the API error for wrong credentials', async () => {
    mockFetch({
      'POST /api/v1/auth/login/': () => ({ status: 400, body: { error: { code: 'invalid_credentials', message: 'Email or password is incorrect.' } } }),
    })
    const { wrapper } = await mountAs(null, LoginView, {}, '/login')
    await wrapper.get('input[type="email"]').setValue('sam@example.com')
    await wrapper.get('input[type="password"]').setValue('wrong')
    await wrapper.get('form').trigger('submit')
    await flush()
    expect(wrapper.get('[role="alert"]').text()).toBe('Email or password is incorrect.')
  })

  it('explains that the session ended and returns to the page afterwards', async () => {
    mockFetch({
      'POST /api/v1/auth/login/': () => ({ body: sessionFor('manager') }),
      'GET /api/v1/billing/subscription/': () => ({ body: { can_write: true } }),
    })
    const { wrapper, router } = await mountAs(null, LoginView, {}, '/login?expired=1&next=/orders')
    expect(wrapper.text()).toContain('Your session has ended')
    await wrapper.get('input[type="email"]').setValue('sam@example.com')
    await wrapper.get('input[type="password"]').setValue('right-password')
    await wrapper.get('form').trigger('submit')
    await vi.waitFor(() => expect(router.currentRoute.value.fullPath).toBe('/orders'))
  })
})
