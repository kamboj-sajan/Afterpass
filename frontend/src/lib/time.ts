/** IST clock and ISO-week helpers. India has no daylight saving, so IST is a fixed UTC+05:30. */

const IST_OFFSET_MS = 5.5 * 3600 * 1000
export const HOUR_MS = 3600 * 1000
export const DAY_MS = 24 * HOUR_MS

/** Polar-orbiting fire satellites pass over Punjab at about 13:30 IST. */
export const OVERPASS_HOUR = 13.5
/** Most large farm fires now start between 15:00 and 19:00 IST (iFOREST). */
export const BURN_WINDOW_HOURS: [number, number] = [15, 19]
/** Sentinel-2 passes at about 11:00 IST; scars first seen on a date appear from then. */
export const SENTINEL_PASS_HOUR = 11

/** Epoch milliseconds for an IST calendar date and hour. */
export function istMs(isoDate: string, hour = 0): number {
  const [year, month, day] = isoDate.split('-').map(Number)
  return Date.UTC(year, month - 1, day) - IST_OFFSET_MS + hour * HOUR_MS
}

/** IST calendar date (YYYY-MM-DD) and fractional hour for an instant. */
export function istParts(ms: number): { date: string; hour: number } {
  const shifted = new Date(ms + IST_OFFSET_MS)
  const date = shifted.toISOString().slice(0, 10)
  const hour = shifted.getUTCHours() + shifted.getUTCMinutes() / 60 + shifted.getUTCSeconds() / 3600
  return { date, hour }
}

function isoDate(utcMidnight: number): string {
  return new Date(utcMidnight).toISOString().slice(0, 10)
}

/** The seven IST dates (Monday first) of an ISO week label such as 2025-W45. */
export function weekDates(week: string): string[] {
  const match = /^(\d{4})-W(\d{2})$/.exec(week)
  if (!match) throw new Error(`Not an ISO week label: ${week}`)
  const year = Number(match[1])
  const index = Number(match[2])
  // 4 January is always in ISO week 1.
  const jan4 = Date.UTC(year, 0, 4)
  const weekday = (new Date(jan4).getUTCDay() + 6) % 7 // Monday = 0
  const monday = jan4 - weekday * DAY_MS + (index - 1) * 7 * DAY_MS
  return Array.from({ length: 7 }, (_, offset) => isoDate(monday + offset * DAY_MS))
}

/** Start (Monday 00:00 IST) and end (next Monday 00:00 IST) of an ISO week. */
export function weekRange(week: string): { start: number; end: number } {
  const dates = weekDates(week)
  const start = istMs(dates[0])
  return { start, end: start + 7 * DAY_MS }
}

/** ISO week label for an IST date. */
export function isoWeekOf(date: string): string {
  const [year, month, day] = date.split('-').map(Number)
  const utc = Date.UTC(year, month - 1, day)
  const weekday = (new Date(utc).getUTCDay() + 6) % 7
  const thursday = utc + (3 - weekday) * DAY_MS
  const weekYear = new Date(thursday).getUTCFullYear()
  const firstThursday = Date.UTC(weekYear, 0, 4)
  const firstWeekday = (new Date(firstThursday).getUTCDay() + 6) % 7
  const weekOneMonday = firstThursday - firstWeekday * DAY_MS
  const index = Math.floor((thursday - weekOneMonday) / (7 * DAY_MS)) + 1
  return `${weekYear}-W${String(index).padStart(2, '0')}`
}
