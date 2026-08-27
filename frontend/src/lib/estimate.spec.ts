import { describe, expect, it } from 'vitest'

import { estimateTotals, type DraftLine } from './estimate'

const line = (quantity: string, unit_price: string, taxable = true): DraftLine => ({ kind: 'labor', part: null, description: '', quantity, unit_price, taxable })

describe('estimateTotals', () => {
  it('matches the server: tax is rounded once on the taxable sum', () => {
    // Same figures as the backend lifecycle test: 89.99 + 50.00 at 10% tax.
    expect(estimateTotals([line('1', '89.99'), line('1', '50.00')], '10.00')).toEqual({ subtotal: '139.99', tax: '14.00', total: '153.99' })
  })

  it('rounds line totals half up and skips untaxed lines', () => {
    expect(estimateTotals([line('0.5', '45.01'), line('3', '10', false)], '20')).toEqual({ subtotal: '52.51', tax: '4.50', total: '57.01' })
  })

  it('treats unparseable input as zero rather than NaN', () => {
    expect(estimateTotals([line('abc', '10')], '20')).toEqual({ subtotal: '0.00', tax: '0.00', total: '0.00' })
  })
})
