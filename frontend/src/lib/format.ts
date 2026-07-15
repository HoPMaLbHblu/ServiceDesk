/** Display helpers. Amounts stay strings end to end and are only formatted here. */

export function money(amount: string | number | null | undefined, currency = 'USD'): string {
  if (amount === null || amount === undefined || amount === '') return '—'
  const value = typeof amount === 'number' ? amount : Number(amount)
  if (Number.isNaN(value)) return String(amount)
  return new Intl.NumberFormat(undefined, { style: 'currency', currency }).format(value)
}

export function dateTime(iso: string | null | undefined, timeZone?: string): string {
  if (!iso) return '—'
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short', timeZone }).format(new Date(iso))
}

export function date(value: string | null | undefined, timeZone?: string): string {
  if (!value) return '—'
  // Plain dates (YYYY-MM-DD) have no timezone; render them as-is.
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    const [y, m, d] = value.split('-').map(Number)
    return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeZone: 'UTC' }).format(new Date(Date.UTC(y!, m! - 1, d!)))
  }
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeZone }).format(new Date(value))
}

export function time(iso: string, timeZone?: string): string {
  return new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit', timeZone }).format(new Date(iso))
}

/** Parts of a date in a given timezone, used for calendar layout. */
export function zonedParts(iso: string | Date, timeZone: string) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(typeof iso === 'string' ? new Date(iso) : iso)
  const get = (type: string) => Number(parts.find((p) => p.type === type)?.value)
  return { year: get('year'), month: get('month'), day: get('day'), hour: get('hour'), minute: get('minute') }
}

/** Convert a wall-clock time in ``timeZone`` to a UTC ISO string. */
export function zonedToUtc(dateStr: string, timeStr: string, timeZone: string): string {
  const [y, m, d] = dateStr.split('-').map(Number)
  const [hh, mm] = timeStr.split(':').map(Number)
  const guess = Date.UTC(y!, m! - 1, d!, hh!, mm!)
  // Find the offset of the zone at that instant, then correct once more for DST edges.
  let utc = guess
  for (let i = 0; i < 2; i++) {
    const p = zonedParts(new Date(utc), timeZone)
    const asUtc = Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute)
    utc += guess - asUtc
  }
  return new Date(utc).toISOString()
}

export const STATUS_LABELS: Record<string, string> = {
  new: 'New',
  scheduled: 'Scheduled',
  diagnosing: 'Diagnosing',
  awaiting_approval: 'Awaiting approval',
  in_progress: 'In progress',
  ready_for_pickup: 'Ready for pickup',
  completed: 'Completed',
  cancelled: 'Cancelled',
}

export const PAYMENT_LABELS: Record<string, string> = {
  not_invoiced: 'Not invoiced',
  unpaid: 'Unpaid',
  partially_paid: 'Partially paid',
  paid: 'Paid',
  refunded: 'Refunded',
}

export function label(value: string): string {
  return value.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())
}
