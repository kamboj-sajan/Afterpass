/** Display formatting: Indian number grouping and IST dates (project rule 10). */

const TIME_ZONE = 'Asia/Kolkata'

const integer = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 })
const oneDecimal = new Intl.NumberFormat('en-IN', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
const percent = new Intl.NumberFormat('en-IN', { style: 'percent', maximumFractionDigits: 0 })

export function formatInteger(value: number): string {
  return integer.format(value)
}

/** Hectares: whole numbers from 100 ha up, one decimal below. */
export function formatHectares(value: number): string {
  return Math.abs(value) >= 100 ? integer.format(value) : oneDecimal.format(value)
}

export function formatShare(share: number | null): string {
  return share === null ? '–' : percent.format(share)
}

function locale(language: string): string {
  return language.startsWith('hi') ? 'hi-IN-u-nu-latn' : 'en-IN'
}

function toDate(value: string | number): Date {
  // A bare YYYY-MM-DD is an IST calendar date.
  return typeof value === 'number' ? new Date(value) : new Date(`${value}T00:00:00+05:30`)
}

/** 3 Nov or 3 Nov 2025. */
export function formatDate(value: string | number, language: string, withYear = false): string {
  return new Intl.DateTimeFormat(locale(language), {
    day: 'numeric',
    month: 'short',
    year: withYear ? 'numeric' : undefined,
    timeZone: TIME_ZONE,
  }).format(toDate(value))
}

/** Mon 3 Nov, 13:30 */
export function formatDateTime(ms: number, language: string): string {
  return new Intl.DateTimeFormat(locale(language), {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: TIME_ZONE,
  }).format(new Date(ms))
}

/** 13:35 */
export function formatTime(value: string | number, language: string): string {
  return new Intl.DateTimeFormat(locale(language), {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: TIME_ZONE,
  }).format(new Date(value))
}

/** 3–9 Nov for a list of the week's dates. */
export function formatDateRange(first: string, last: string, language: string): string {
  const sameMonth = first.slice(0, 7) === last.slice(0, 7)
  const day = new Intl.DateTimeFormat(locale(language), { day: 'numeric', timeZone: TIME_ZONE })
  return sameMonth
    ? `${day.format(toDate(first))}–${formatDate(last, language)}`
    : `${formatDate(first, language)} – ${formatDate(last, language)}`
}
