import { describe, expect, it } from 'vitest'
import {
  cityStats,
  defaultLocality,
  delhiMean,
  hourIndex,
  nextRun,
  peakRun,
  peakWindow,
  placeName,
  runForClock,
  runStartMs,
  saiLevel,
  searchLocalities,
} from './smoke'
import { istMs } from './time'
import type { DelhiSai, SmokeLocality, SmokeRunSummary } from './types'

function run(runId: string, kind: 'replay' | 'live' = 'replay'): SmokeRunSummary {
  return {
    run_id: runId,
    kind,
    start: (runStartMs(runId) ?? Number.NaN) / 1000,
    start_ist: '',
    hours: 48,
    peak_sai: 0,
    peak_level: 'low',
    delhi_mean_peak: 0,
    delhi_mean_peak_hour: 0,
    trips: 0,
    trips_mb: 0,
  }
}

function locality(name: string, sai: number[], nameHi?: string): SmokeLocality {
  return { id: name, name, name_hi: nameHi, district: 'D', lon: 77, lat: 28.6, h3: 'x', sai }
}

describe('saiLevel', () => {
  it('uses the brief’s four levels', () => {
    expect([0, 24, 25, 49, 50, 75, 100].map(saiLevel)).toEqual([
      'low',
      'low',
      'moderate',
      'moderate',
      'high',
      'very_high',
      'very_high',
    ])
  })
})

describe('runs', () => {
  const runs = [run('2025-11-02'), run('2025-11-03'), run('2025-11-04')]

  it('parses replay and live run ids as IST', () => {
    expect(runStartMs('2025-11-03')).toBe(istMs('2025-11-03'))
    expect(runStartMs('2026-10-11T1912')).toBe(istMs('2026-10-11', 19.2))
    expect(runStartMs('latest')).toBeNull()
  })

  it('picks the run that starts on the clock’s day, not the overlapping one from the day before', () => {
    expect(runForClock(runs, istMs('2025-11-03', 15))?.run_id).toBe('2025-11-03')
    expect(runForClock(runs, istMs('2025-11-05', 23))?.run_id).toBe('2025-11-04')
    expect(runForClock(runs, istMs('2025-11-01', 12))).toBeNull()
  })

  it('finds the next run of the same kind', () => {
    expect(nextRun(runs, runs[0])?.run_id).toBe('2025-11-03')
    expect(nextRun(runs, runs[2])).toBeNull()
  })

  it('clamps the hour to the run', () => {
    const r = runs[1]
    expect(hourIndex(r, istMs('2025-11-03', 5.5))).toBe(5)
    expect(hourIndex(r, istMs('2025-11-02', 5))).toBe(0)
    expect(hourIndex(r, istMs('2025-11-09'))).toBe(47)
  })
})

describe('peakWindow', () => {
  const hours = Array.from({ length: 8 }, (_, i) => 1_762_108_200 + i * 3600)

  it('spans the hours at or above half the peak', () => {
    const window = peakWindow(hours, [5, 20, 40, 80, 70, 30, 45, 10])
    if (window === null) throw new Error('expected a peak')
    expect(window.peak).toBe(80)
    expect(window.level).toBe('very_high')
    expect(window.start).toBe(hours[2] * 1000)
    // 30 is under half the peak, so the window ends with the hour that had 70.
    expect(window.end).toBe(hours[4] * 1000 + 3_600_000)
  })

  it('has no peak when the index never reaches Moderate', () => {
    expect(peakWindow(hours, [0, 10, 24, 3, 0, 0, 0, 0])).toBeNull()
  })
})

describe('localities', () => {
  const items = [
    locality('Dwarka', [10, 20], 'द्वारका'),
    locality('Old Dwarka Road', [50, 60]),
    locality('Rohini', [90, 5], 'रोहिणी'),
  ]

  it('matches English and Hindi names, prefix matches first', () => {
    expect(searchLocalities(items, 'dwar').map((i) => i.name)).toEqual(['Dwarka', 'Old Dwarka Road'])
    expect(searchLocalities(items, 'द्वार').map((i) => i.name)).toEqual(['Dwarka'])
    expect(searchLocalities(items, 'रोहि').map((i) => i.name)).toEqual(['Rohini'])
    expect(searchLocalities(items, '  ')).toEqual([])
  })

  it('defaults to the preferred name, else the worst peak', () => {
    expect(defaultLocality(items, 'dwarka')?.name).toBe('Dwarka')
    expect(defaultLocality(items, 'Nowhere')?.name).toBe('Rohini')
  })

  it('averages Delhi cells per hour', () => {
    const sai = { hours: [1, 2], cells: { a: [10, 0], b: [30, 50] } } as unknown as DelhiSai
    expect(delhiMean(sai)).toEqual([20, 25])
  })
})

describe('Delhi screen helpers', () => {
  it('opens on the run with the highest Delhi-wide hour, the earliest of equals', () => {
    const runs = [run('2025-11-05'), run('2025-11-06'), run('2025-11-07'), run('2025-11-08')]
    runs[0].delhi_mean_peak = 98.1
    runs[1].delhi_mean_peak = 98.9
    runs[2].delhi_mean_peak = 98.9
    runs[3].delhi_mean_peak = 91.3
    expect(peakRun(runs)?.run_id).toBe('2025-11-06')
    expect(peakRun([])).toBeNull()
  })

  it('summarises one hour across Delhi', () => {
    const sai = { hours: [0, 3600], cells: { a: [0, 80], b: [10, 50], c: [20, 49], d: [30, 0] } } as unknown as DelhiSai
    expect(cityStats(sai, 0)).toEqual({ mean: 15, high: 0, cells: 4 })
    expect(cityStats(sai, 1)).toEqual({ mean: 44.75, high: 2, cells: 4 })
  })

  it('names a place in Hindi only when a Hindi name is known', () => {
    const base = { id: 'x', district: 'West', lon: 0, lat: 0, h3: '', sai: [] }
    const dwarka: SmokeLocality = { ...base, name: 'Dwarka', name_hi: 'द्वारका' }
    const other: SmokeLocality = { ...base, name: 'Rattan Park' }
    expect(placeName(dwarka, 'hi')).toBe('द्वारका')
    expect(placeName(dwarka, 'en')).toBe('Dwarka')
    expect(placeName(other, 'hi')).toBe('Rattan Park')
  })
})
