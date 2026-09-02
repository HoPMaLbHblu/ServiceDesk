import { afterEach, describe, expect, it } from 'vitest'

import type { OrderDetail } from '@/api/types'
import { mockFetch } from '@/test/fetch'
import { flush, mountAs } from '@/test/mount'

import OrderDetailsCard from './OrderDetailsCard.vue'

afterEach(() => document.body.replaceChildren())

const order = {
  id: 'o1',
  number: 7,
  reference: 'RO-00007',
  customer: { id: 'c1', name: 'Amira Hassan' },
  device_label: 'Galaxy S21',
  device: { id: 'd1', brand: 'Samsung', model: 'Galaxy S21' },
  status: 'diagnosing',
  status_label: 'Diagnosing',
  priority: 'normal',
  assigned_technician: null,
  problem_description: 'Not charging',
  version: 3,
  allowed_transitions: ['awaiting_approval', 'cancelled'],
  created_at: '2026-10-01T10:00:00Z',
  updated_at: '2026-10-01T10:00:00Z',
} as unknown as OrderDetail

describe('OrderDetailsCard', () => {
  it('explains an edit conflict instead of overwriting someone else’s change', async () => {
    const { calls } = mockFetch({
      'GET /api/v1/members/staff_options/': () => ({ body: [] }),
      'PATCH /api/v1/orders/o1/': () => ({
        status: 409,
        body: { error: { code: 'stale_version', message: 'This order was changed by someone else.', details: { current_version: 4 } } },
      }),
    })
    const { wrapper } = await mountAs('manager', OrderDetailsCard, { order })
    await wrapper.get('button').trigger('click') // Edit
    await wrapper.get('textarea').setValue('Not charging, port loose')
    await wrapper.get('form').trigger('submit')
    await flush()

    const patch = calls.find((c) => c.method === 'PATCH')
    expect(patch?.json).toMatchObject({ version: 3, problem_description: 'Not charging, port loose' })
    expect(wrapper.get('[data-testid="conflict"]').text()).toContain('Someone else changed this order')
    // The user's text is kept so they can re-apply it after reloading.
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('Not charging, port loose')
  })

  it('shows field errors returned by the API', async () => {
    mockFetch({
      'GET /api/v1/members/staff_options/': () => ({ body: [] }),
      'PATCH /api/v1/orders/o1/': () => ({
        status: 400,
        body: { error: { code: 'validation_error', message: 'Invalid input.', fields: { expected_completion_date: ['Date cannot be in the past.'] } } },
      }),
    })
    const { wrapper } = await mountAs('manager', OrderDetailsCard, { order })
    await wrapper.get('button').trigger('click')
    await wrapper.get('form').trigger('submit')
    await flush()
    expect(wrapper.text()).toContain('Date cannot be in the past.')
    expect(wrapper.find('input[type="date"]').attributes('aria-invalid')).toBe('true')
  })

  it('does not offer editing to technicians', async () => {
    mockFetch({ 'GET /api/v1/members/staff_options/': () => ({ body: [] }) })
    const { wrapper } = await mountAs('technician', OrderDetailsCard, { order })
    expect(wrapper.find('button').exists()).toBe(false)
  })
})
