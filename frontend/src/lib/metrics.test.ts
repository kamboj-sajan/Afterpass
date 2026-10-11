import { describe, expect, it } from 'vitest'
import { coverageNotes, hourHistogram, kpis, seasonWeeks, topVillages, weeklySeries } from './metrics'
import type { DistrictSummary, Summary, Village } from './types'

function district(name: string, overrides: Partial<DistrictSummary> = {}): DistrictSummary {
  const hours = Array.from({ length: 24 }, () => 0)
  hours[13] = 3
  return {
    district: name,
    state: 'Punjab',
    cropland_ha: 1000,
    burned_ha: 30,
    recorded_ha: 10,
    unrecorded_ha: 20,
    unrecorded_share: 0.667,
    scar_count: 6,
    firms: {
      firms_count: 4,
      by_satellite: { VIIRS_SNPP_SP: 4 },
      by_day: { '2025-11-02': 1, '2025-11-04': 3 },
      by_ist_hour: hours,
    },
    by_day: [],
    by_week: [
      { week: '2025-W44', burned_ha: 10, recorded_ha: 10, unrecorded_ha: 0, unrecorded_share: 0, scar_count: 2 },
      { week: '2025-W45', burned_ha: 20, recorded_ha: 0, unrecorded_ha: 20, unrecorded_share: 1, scar_count: 4 },
    ],
    sentinel2: [
      { date: '2025-11-02', valid_pct: 100, scars: 2, burned_ha: 10 },
      { date: '2025-11-04', valid_pct: 40, scars: 4, burned_ha: 20 },
    ],
    missing_dates: [],
    ...overrides,
  }
}

const summary: Summary = {
  season: 2025,
  window: ['2025-10-01', '2025-11-30'],
  totals: { burned_ha: 60, recorded_ha: 20, unrecorded_ha: 40, unrecorded_share: 0.667, scar_count: 12 },
  firms: { firms_count: 8, by_satellite: {}, by_day: {}, by_ist_hour: [] },
  districts: [district('Sangrur'), district('Bathinda', { missing_dates: ['2025-11-06'] })],
  limitations: [],
  generated_at: '2026-10-11T11:10:05+00:00',
  source_versions: {},
  demo: false,
}

describe('kpis', () => {
  it('sums the season for the chosen districts', () => {
    expect(kpis(summary, ['Sangrur', 'Bathinda'], 'season', null)).toEqual({
      officialDetections: 8,
      burnedHa: 60,
      recordedHa: 20,
      unrecordedHa: 40,
      unrecordedShare: 40 / 60,
      scarCount: 12,
    })
  })

  it('restricts to one week and one district', () => {
    expect(kpis(summary, ['Sangrur'], 'week', '2025-W45')).toEqual({
      officialDetections: 3, // only 4 Nov falls in week 45
      burnedHa: 20,
      recordedHa: 0,
      unrecordedHa: 20,
      unrecordedShare: 1,
      scarCount: 4,
    })
  })

  it('has no share when nothing burned', () => {
    expect(kpis(summary, ['Sangrur'], 'week', '2025-W40').unrecordedShare).toBeNull()
    expect(kpis(summary, [], 'season', null).burnedHa).toBe(0)
  })
})

describe('series', () => {
  it('adds districts week by week', () => {
    expect(weeklySeries(summary, ['Sangrur', 'Bathinda'])).toEqual([
      { week: '2025-W44', recorded_ha: 20, unrecorded_ha: 0 },
      { week: '2025-W45', recorded_ha: 0, unrecorded_ha: 40 },
    ])
    expect(seasonWeeks(summary)).toEqual(['2025-W44', '2025-W45'])
  })

  it('adds the IST-hour histograms', () => {
    const hours = hourHistogram(summary, ['Sangrur', 'Bathinda'])
    expect(hours).toHaveLength(24)
    expect(hours[13]).toBe(6)
  })
})

describe('topVillages', () => {
  const villages: Village[] = [
    {
      id: 'a',
      name: 'Alpha',
      district: 'Sangrur',
      lon: 75.9,
      lat: 30.2,
      burned_ha: 50,
      unrecorded_ha: 40,
      share: 0.8,
      weekly: [{ week: '2025-W45', burned_ha: 10, unrecorded_ha: 5 }],
    },
    {
      id: 'b',
      name: 'Beta',
      district: 'Sangrur',
      lon: 75.9,
      lat: 30.2,
      burned_ha: 30,
      unrecorded_ha: 30,
      share: 1,
      weekly: [{ week: '2025-W45', burned_ha: 30, unrecorded_ha: 30 }],
    },
    {
      id: 'c',
      name: 'Gamma',
      district: 'Bathinda',
      lon: 75.0,
      lat: 30.2,
      burned_ha: 90,
      unrecorded_ha: 90,
      share: 1,
      weekly: [],
    },
    {
      id: 'd',
      name: 'Delta',
      district: 'Sangrur',
      lon: 75.9,
      lat: 30.2,
      burned_ha: 5,
      unrecorded_ha: 0,
      share: 0,
      weekly: [],
    },
  ]

  it('ranks by unrecorded hectares in the season and drops villages with none', () => {
    const ranked = topVillages(villages, ['Sangrur', 'Bathinda'], 'season', null, 10)
    expect(ranked.map((entry) => entry.village.id)).toEqual(['c', 'a', 'b'])
  })

  it('uses the week when scoped to one, and respects the district filter and limit', () => {
    const ranked = topVillages(villages, ['Sangrur'], 'week', '2025-W45', 1)
    expect(ranked).toEqual([{ village: villages[1], burnedHa: 30, unrecordedHa: 30 }])
  })
})

describe('coverageNotes', () => {
  it('reports missing passes, weeks without a pass and thin coverage', () => {
    expect(coverageNotes(summary, ['Sangrur'], '2025-W45')).toEqual([
      { kind: 'partial', district: 'Sangrur', bestPct: 40 },
    ])
    expect(coverageNotes(summary, ['Bathinda'], '2025-W45')).toEqual([
      { kind: 'missing', district: 'Bathinda', dates: ['2025-11-06'] },
      { kind: 'partial', district: 'Bathinda', bestPct: 40 },
    ])
    expect(coverageNotes(summary, ['Sangrur'], '2025-W47')).toEqual([{ kind: 'no-pass', district: 'Sangrur' }])
    expect(coverageNotes(summary, ['Sangrur'], '2025-W44')).toEqual([])
  })
})
