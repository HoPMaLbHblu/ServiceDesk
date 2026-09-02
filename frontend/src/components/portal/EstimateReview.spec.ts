import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import type { PublicEstimate } from '@/api/types'

import EstimateReview from './EstimateReview.vue'

const estimate = {
  id: 'e1',
  business_name: 'Alpha Repairs',
  order_reference: 'RO-00002',
  device: 'Apple iPhone 13',
  customer_name: 'Chris Customer',
  version: 2,
  status: 'sent',
  notes: '',
  currency: 'GBP',
  tax_rate: '20.00',
  subtotal: '71.50',
  tax_total: '14.30',
  total: '85.80',
  valid_until: '2026-10-21',
  content_hash: 'hash-v2',
  decided_at: null,
  decided_by_name: '',
  lines: [{ kind: 'part', description: 'Battery', quantity: '1.00', unit_price: '49.00', line_total: '49.00', taxable: true }],
} as unknown as PublicEstimate

describe('EstimateReview', () => {
  it('approves the exact version shown by sending its content hash', async () => {
    const wrapper = mount(EstimateReview, { props: { estimate, canDecide: true, askName: true } })
    expect(wrapper.text()).toContain('£85.80')
    await wrapper.get('[data-testid="approve-estimate"]').trigger('click')
    expect(wrapper.emitted('decide')?.[0]?.[0]).toEqual({ decision: 'approve', note: '', name: 'Chris Customer', content_hash: 'hash-v2' })
  })

  it('asks for confirmation before declining', async () => {
    const wrapper = mount(EstimateReview, { props: { estimate, canDecide: true } })
    await wrapper.findAll('button').find((b) => b.text() === 'Decline')!.trigger('click')
    expect(wrapper.emitted('decide')).toBeUndefined()
    await wrapper.get('textarea').setValue('Too expensive')
    await wrapper.findAll('button').find((b) => b.text() === 'Decline estimate')!.trigger('click')
    expect(wrapper.emitted('decide')?.[0]?.[0]).toMatchObject({ decision: 'reject', note: 'Too expensive' })
  })

  it('requires a name on the public link', async () => {
    const wrapper = mount(EstimateReview, { props: { estimate, canDecide: true, askName: true } })
    await wrapper.get('#approver-name').setValue('  ')
    expect(wrapper.get('[data-testid="approve-estimate"]').attributes('disabled')).toBeDefined()
  })

  it('shows the recorded decision and no buttons once decided', () => {
    const decided = { ...estimate, status: 'approved', decided_at: '2026-10-07T12:00:00Z', decided_by_name: 'Chris Customer' }
    const wrapper = mount(EstimateReview, { props: { estimate: decided, canDecide: false } })
    expect(wrapper.text()).toContain('Approved by Chris Customer')
    expect(wrapper.find('[data-testid="approve-estimate"]').exists()).toBe(false)
  })
})
