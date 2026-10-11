import { describe, expect, it } from 'vitest'
import { DAY_MS, isoWeekOf, istMs, istParts, weekDates, weekRange } from './time'

describe('IST clock', () => {
  it('converts an IST date and hour to an instant', () => {
    // 13:30 IST is 08:00 UTC.
    expect(new Date(istMs('2025-11-03', 13.5)).toISOString()).toBe('2025-11-03T08:00:00.000Z')
    // Midnight IST is the previous UTC evening.
    expect(new Date(istMs('2025-11-03')).toISOString()).toBe('2025-11-02T18:30:00.000Z')
  })

  it('reads the IST date and hour back', () => {
    expect(istParts(Date.parse('2025-11-02T20:10:00Z'))).toEqual({
      date: '2025-11-03',
      hour: 1 + 40 / 60,
    })
  })
})

describe('ISO weeks', () => {
  it('lists Monday to Sunday', () => {
    expect(weekDates('2025-W45')).toEqual([
      '2025-11-03',
      '2025-11-04',
      '2025-11-05',
      '2025-11-06',
      '2025-11-07',
      '2025-11-08',
      '2025-11-09',
    ])
    expect(weekDates('2026-W01')[0]).toBe('2025-12-29')
  })

  it('agrees with the labels the pipeline writes', () => {
    expect(isoWeekOf('2025-11-02')).toBe('2025-W44') // Sunday closes the week
    expect(isoWeekOf('2025-11-03')).toBe('2025-W45')
    expect(isoWeekOf('2025-12-29')).toBe('2026-W01')
    for (const day of weekDates('2025-W40')) expect(isoWeekOf(day)).toBe('2025-W40')
  })

  it('spans exactly seven IST days', () => {
    const { start, end } = weekRange('2025-W45')
    expect(end - start).toBe(7 * DAY_MS)
    expect(istParts(start)).toEqual({ date: '2025-11-03', hour: 0 })
  })

  it('rejects anything that is not a week label', () => {
    expect(() => weekDates('2025-11-03')).toThrow()
  })
})
