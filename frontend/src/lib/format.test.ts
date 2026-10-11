import { describe, expect, it } from 'vitest'
import { formatDate, formatDateRange, formatHectares, formatInteger, formatShare, formatTime } from './format'

describe('number formatting', () => {
  it('uses Indian digit grouping', () => {
    expect(formatInteger(179105)).toBe('1,79,105')
    expect(formatInteger(1205)).toBe('1,205')
  })

  it('shows small areas with one decimal and large ones as whole hectares', () => {
    expect(formatHectares(161455.5)).toBe('1,61,456')
    expect(formatHectares(42.25)).toBe('42.3')
  })

  it('formats shares as whole percentages and missing shares as a dash', () => {
    expect(formatShare(0.643)).toBe('64%')
    expect(formatShare(null)).toBe('–')
  })
})

describe('date formatting', () => {
  it('treats bare dates as IST calendar dates', () => {
    expect(formatDate('2025-11-03', 'en')).toBe('3 Nov')
    expect(formatDate('2025-11-03', 'en', true)).toBe('3 Nov 2025')
  })

  it('shows instants in IST', () => {
    expect(formatTime('2025-11-03T13:35+05:30', 'en')).toBe('13:35')
    expect(formatTime(Date.parse('2025-11-02T20:10:00Z'), 'en')).toBe('01:40')
  })

  it('shortens ranges inside one month', () => {
    expect(formatDateRange('2025-11-03', '2025-11-09', 'en')).toBe('3–9 Nov')
    expect(formatDateRange('2025-10-27', '2025-11-02', 'en')).toBe('27 Oct – 2 Nov')
  })

  it('keeps Latin digits in Hindi', () => {
    expect(formatDate('2025-11-03', 'hi')).toMatch(/^3 /)
  })
})
