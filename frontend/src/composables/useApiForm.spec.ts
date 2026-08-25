import { describe, expect, it } from 'vitest'

import { ApiError } from '@/api/client'

import { useApiForm } from './useApiForm'

describe('useApiForm', () => {
  it('shows field errors next to fields and a summary at the top', async () => {
    const form = useApiForm({ email: '', password: '' })
    await form.submit(() =>
      Promise.reject(new ApiError(400, { code: 'validation_error', message: 'Invalid input.', fields: { email: ['Enter a valid email.'] } })),
    )
    expect(form.fieldError('email')).toBe('Enter a valid email.')
    expect(form.fieldError('password')).toBeUndefined()
    expect(form.generalError.value).toBe('Please correct the highlighted fields.')
    expect(form.submitting.value).toBe(false)
  })

  it('shows non-field API errors as the general message', async () => {
    const form = useApiForm({ email: '' })
    await form.submit(() => Promise.reject(new ApiError(402, { code: 'staff_limit_reached', message: 'Your plan allows 3 team members.' })))
    expect(form.generalError.value).toBe('Your plan allows 3 team members.')
  })

  it('reports network failures without leaking internals', async () => {
    const form = useApiForm({ email: '' })
    await form.submit(() => Promise.reject(new TypeError('Failed to fetch')))
    expect(form.generalError.value).toMatch(/connection/)
  })

  it('tracks unsaved changes and clears errors on success', async () => {
    const form = useApiForm({ name: 'A' })
    expect(form.dirty.value).toBe(false)
    form.values.name = 'B'
    expect(form.dirty.value).toBe(true)
    const result = await form.submit(async () => 'ok')
    expect(result).toBe('ok')
    expect(form.dirty.value).toBe(false)
    expect(form.generalError.value).toBeNull()
  })
})
