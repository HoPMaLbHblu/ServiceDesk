/**
 * Client-side preview of estimate totals. The server recalculates and is the
 * source of truth; this mirrors its rules (round each line to cents, then
 * apply tax once to the taxable sum, half-up) so the preview matches.
 */
export interface DraftLine {
  kind: 'labor' | 'part' | 'fee'
  part: string | null
  description: string
  quantity: string
  unit_price: string
  taxable: boolean
}

function toCents(value: string): bigint | null {
  const match = /^\s*(\d+)(?:\.(\d*))?\s*$/.exec(value)
  if (!match) return null
  const frac = (match[2] ?? '').padEnd(4, '0').slice(0, 4)
  return BigInt(match[1]!) * 10000n + BigInt(frac) // ten-thousandths
}

function roundHalfUp(numerator: bigint, denominator: bigint): bigint {
  return (numerator * 2n + denominator) / (denominator * 2n)
}

function format(cents: bigint): string {
  const sign = cents < 0n ? '-' : ''
  const abs = cents < 0n ? -cents : cents
  return `${sign}${abs / 100n}.${String(abs % 100n).padStart(2, '0')}`
}

export function lineTotalCents(line: Pick<DraftLine, 'quantity' | 'unit_price'>): bigint {
  const q = toCents(line.quantity)
  const p = toCents(line.unit_price)
  if (q === null || p === null) return 0n
  // q and p are in 1/10000 units; product is 1/1e8; cents are 1/100.
  return roundHalfUp(q * p, 1_000_000n)
}

export function estimateTotals(lines: DraftLine[], taxRate: string) {
  let subtotal = 0n
  let taxable = 0n
  for (const line of lines) {
    const total = lineTotalCents(line)
    subtotal += total
    if (line.taxable) taxable += total
  }
  const rate = toCents(taxRate) ?? 0n // percent in 1/10000
  const tax = roundHalfUp(taxable * rate, 1_000_000n)
  return { subtotal: format(subtotal), tax: format(tax), total: format(subtotal + tax) }
}
