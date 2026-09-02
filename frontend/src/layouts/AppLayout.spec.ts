import { afterEach, describe, expect, it } from 'vitest'

import { mockFetch } from '@/test/fetch'
import { flush, mountAs } from '@/test/mount'

import AppLayout from './AppLayout.vue'

afterEach(() => document.body.replaceChildren())

function stubSubscription() {
  mockFetch({ 'GET /api/v1/billing/subscription/': () => ({ body: { status: 'active', can_write: true, read_only_reason: '' } }) })
}

describe('navigation by role', () => {
  it('hides money and reports from technicians', async () => {
    stubSubscription()
    const { wrapper } = await mountAs('technician', AppLayout)
    const nav = wrapper.get('nav[aria-label="Main"]').text()
    expect(nav).toContain('Repair orders')
    expect(nav).not.toContain('Invoices')
    expect(nav).not.toContain('Reports')
  })

  it('shows invoices to managers and reports only to owners', async () => {
    stubSubscription()
    const manager = await mountAs('manager', AppLayout)
    expect(manager.wrapper.get('nav[aria-label="Main"]').text()).toContain('Invoices')
    expect(manager.wrapper.get('nav[aria-label="Main"]').text()).not.toContain('Reports')
    manager.wrapper.unmount()
    const owner = await mountAs('owner', AppLayout)
    expect(owner.wrapper.get('nav[aria-label="Main"]').text()).toContain('Reports')
  })

  it('shows a read-only banner when the subscription blocks changes', async () => {
    mockFetch({ 'GET /api/v1/billing/subscription/': () => ({ body: { status: 'cancelled', can_write: false, read_only_reason: 'The subscription was cancelled.' } }) })
    const { wrapper } = await mountAs('manager', AppLayout)
    await flush()
    await flush()
    expect(wrapper.get('[data-testid="read-only-banner"]').text()).toContain('The subscription was cancelled.')
    expect(wrapper.text()).toContain('Ask the owner')
  })
})
