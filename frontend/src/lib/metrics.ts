/** Pure selectors that turn the published files into what the panels show. */

import { weekDates } from './time'
import type { DistrictSummary, Summary, Totals, Village } from './types'

export type Scope = 'week' | 'season'

export interface Kpis {
  officialDetections: number
  burnedHa: number
  recordedHa: number
  unrecordedHa: number
  unrecordedShare: number | null
  scarCount: number
}

export function selectedDistricts(summary: Summary, names: string[]): DistrictSummary[] {
  return summary.districts.filter((d) => names.includes(d.district))
}

function sum(rows: Totals[]): Omit<Kpis, 'officialDetections'> {
  const burnedHa = rows.reduce((total, row) => total + row.burned_ha, 0)
  const recordedHa = rows.reduce((total, row) => total + row.recorded_ha, 0)
  const unrecordedHa = rows.reduce((total, row) => total + row.unrecorded_ha, 0)
  return {
    burnedHa,
    recordedHa,
    unrecordedHa,
    unrecordedShare: burnedHa > 0 ? unrecordedHa / burnedHa : null,
    scarCount: rows.reduce((total, row) => total + row.scar_count, 0),
  }
}

/** Headline numbers for the chosen districts, for one week or the whole season. */
export function kpis(summary: Summary, names: string[], scope: Scope, week: string | null): Kpis {
  const districts = selectedDistricts(summary, names)
  if (scope === 'season' || week === null) {
    return {
      officialDetections: districts.reduce((total, d) => total + d.firms.firms_count, 0),
      ...sum(districts),
    }
  }
  const days = new Set(weekDates(week))
  const official = districts.reduce(
    (total, d) =>
      total +
      Object.entries(d.firms.by_day).reduce((count, [day, value]) => (days.has(day) ? count + value : count), 0),
    0,
  )
  const rows = districts.flatMap((d) => d.by_week.filter((row) => row.week === week))
  return { officialDetections: official, ...sum(rows) }
}

export interface WeekPoint {
  week: string
  recorded_ha: number
  unrecorded_ha: number
}

/** Recorded and unrecorded hectares per ISO week, summed over the chosen districts. */
export function weeklySeries(summary: Summary, names: string[]): WeekPoint[] {
  const byWeek = new Map<string, WeekPoint>()
  for (const district of selectedDistricts(summary, names)) {
    for (const row of district.by_week) {
      const point = byWeek.get(row.week) ?? { week: row.week, recorded_ha: 0, unrecorded_ha: 0 }
      point.recorded_ha += row.recorded_ha
      point.unrecorded_ha += row.unrecorded_ha
      byWeek.set(row.week, point)
    }
  }
  return [...byWeek.values()].sort((a, b) => a.week.localeCompare(b.week))
}

/** Every ISO week with data in any district of the season, in order. */
export function seasonWeeks(summary: Summary): string[] {
  const weeks = new Set(summary.districts.flatMap((d) => d.by_week.map((row) => row.week)))
  return [...weeks].sort()
}

/** FIRMS detections by IST hour (24 values), summed over the chosen districts. */
export function hourHistogram(summary: Summary, names: string[]): number[] {
  const hours = Array.from({ length: 24 }, () => 0)
  for (const district of selectedDistricts(summary, names)) {
    district.firms.by_ist_hour.forEach((count, hour) => {
      hours[hour] += count
    })
  }
  return hours
}

export interface RankedVillage {
  village: Village
  burnedHa: number
  unrecordedHa: number
}

/** Villages ranked by unrecorded hectares in scope: "send help here first". */
export function topVillages(
  villages: Village[],
  names: string[],
  scope: Scope,
  week: string | null,
  count: number,
): RankedVillage[] {
  const ranked: RankedVillage[] = []
  for (const village of villages) {
    if (!names.includes(village.district)) continue
    if (scope === 'season' || week === null) {
      ranked.push({ village, burnedHa: village.burned_ha, unrecordedHa: village.unrecorded_ha })
      continue
    }
    const row = village.weekly.find((entry) => entry.week === week)
    if (row) ranked.push({ village, burnedHa: row.burned_ha, unrecordedHa: row.unrecorded_ha })
  }
  return ranked
    .filter((entry) => entry.unrecordedHa > 0)
    .sort((a, b) => b.unrecordedHa - a.unrecordedHa || a.village.id.localeCompare(b.village.id))
    .slice(0, count)
}

export type CoverageNote =
  | { kind: 'missing'; district: string; dates: string[] }
  | { kind: 'no-pass'; district: string }
  | { kind: 'partial'; district: string; bestPct: number }

/** Below this share of cropland visible on the week's best pass, say so. */
const PARTIAL_COVERAGE_PCT = 60

/** Plain-language data gaps for the chosen districts and week. */
export function coverageNotes(summary: Summary, names: string[], week: string | null): CoverageNote[] {
  const notes: CoverageNote[] = []
  const days = week === null ? null : new Set(weekDates(week))
  for (const district of selectedDistricts(summary, names)) {
    const missing = district.missing_dates.filter((day) => days === null || days.has(day))
    if (missing.length > 0) notes.push({ kind: 'missing', district: district.district, dates: missing })
    if (days === null) continue
    const passes = district.sentinel2.filter((pass) => days.has(pass.date))
    if (passes.length === 0) {
      notes.push({ kind: 'no-pass', district: district.district })
    } else {
      const bestPct = Math.max(...passes.map((pass) => pass.valid_pct))
      if (bestPct < PARTIAL_COVERAGE_PCT) notes.push({ kind: 'partial', district: district.district, bestPct })
    }
  }
  return notes
}
