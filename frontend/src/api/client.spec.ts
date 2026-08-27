import { afterEach, describe, expect, it, vi } from 'vitest'

import { mockFetch } from '@/test/fetch'

import { ApiError, api, flattenFields, onUnauthorized } from './client'

afterEach(() => {
  onUnauthorized(null)
  document.cookie = 'csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT'
})

describe('flattenFields', () => {
  it('turns nested serializer errors into dotted paths', () => {
    expect(
      flattenFields({ email: ['Enter a valid email.'], lines: [{}, { quantity: ['Must be positive.'] }], address: { city: 'Required.' } }),
    ).toEqual({ email: ['Enter a valid email.'], 'lines.1.quantity': ['Must be positive.'], 'address.city': ['Required.'] })
  })
})

describe('api client', () => {
  it('sends the CSRF token on unsafe requests only', async () => {
    document.cookie = 'csrftoken=abc123'
    const { calls } = mockFetch({ 'GET /api/v1/orders/': () => ({ body: [] }), 'POST /api/v1/orders/': () => ({ status: 201, body: {} }) })
    await api.get('/orders/')
    await api.post('/orders/', { a: 1 })
    expect(calls[0]!.headers['X-CSRFToken']).toBeUndefined()
    expect(calls[1]!.headers['X-CSRFToken']).toBe('abc123')
    expect(calls[1]!.json).toEqual({ a: 1 })
  })

  it('maps the error envelope to ApiError with code, fields and details', async () => {
    mockFetch({
      'POST /api/v1/orders/x/transition/': () => ({
        status: 409,
        body: { error: { code: 'invalid_transition', message: 'Not allowed.', fields: {}, details: { allowed: ['diagnosing'] } } },
      }),
    })
    const error = await api.post('/orders/x/transition/', {}).catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 409, code: 'invalid_transition', message: 'Not allowed.', isConflict: true, details: { allowed: ['diagnosing'] } })
  })

  it('reports 401 responses so an expired session can be handled, except for auth endpoints', async () => {
    const listener = vi.fn()
    onUnauthorized(listener)
    const body = { error: { code: 'not_authenticated', message: 'Sign in.' } }
    mockFetch({ 'GET /api/v1/orders/': () => ({ status: 401, body }), 'POST /api/v1/auth/login/': () => ({ status: 401, body }) })
    await expect(api.get('/orders/')).rejects.toBeInstanceOf(ApiError)
    await expect(api.post('/auth/login/', {})).rejects.toBeInstanceOf(ApiError)
    expect(listener).toHaveBeenCalledTimes(1)
    expect(listener).toHaveBeenCalledWith('/api/v1/orders/')
  })

  it('builds query strings without empty values', async () => {
    const { calls } = mockFetch({ 'GET /api/v1/orders/': () => ({ body: [] }) })
    await api.get('/orders/', { search: '', status: ['new', 'scheduled'], page: 2, open: undefined })
    expect(calls[0]!.url).toBe('/api/v1/orders/?status=new&status=scheduled&page=2')
  })
})
