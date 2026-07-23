import { zonedParts, zonedToUtc } from './format'

/** Today's date (YYYY-MM-DD) in the given timezone. */
export function todayIn(timeZone: string, now = new Date()): string {
  const p = zonedParts(now, timeZone)
  return `${p.year}-${String(p.month).padStart(2, '0')}-${String(p.day).padStart(2, '0')}`
}

export function addDays(day: string, days: number): string {
  const [y, m, d] = day.split('-').map(Number)
  const date = new Date(Date.UTC(y!, m! - 1, d! + days))
  return date.toISOString().slice(0, 10)
}

/** The UTC range covering whole local days [start, start + days) in the timezone. */
export function dayRange(start: string, days: number, timeZone: string) {
  return { start: zonedToUtc(start, '00:00', timeZone), end: zonedToUtc(addDays(start, days), '00:00', timeZone) }
}

/** Monday of the week containing the given local day. */
export function startOfWeek(day: string): string {
  const [y, m, d] = day.split('-').map(Number)
  const weekday = (new Date(Date.UTC(y!, m! - 1, d!)).getUTCDay() + 6) % 7
  return addDays(day, -weekday)
}

/** Local date (YYYY-MM-DD) of an instant in the timezone. */
export function localDay(iso: string, timeZone: string): string {
  return todayIn(timeZone, new Date(iso))
}
