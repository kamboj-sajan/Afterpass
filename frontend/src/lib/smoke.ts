/** Smoke outlook helpers: the run under the clock, index levels, peak windows and locality search. */

import { HOUR_MS, istMs } from './time'
import type { DelhiSai, SaiLevel, SmokeLocality, SmokeRunSummary } from './types'

/** Lowest index value of each plain-language level (brief §8.4). Mirrors smoke.LEVELS in the backend. */
export const SAI_LEVELS: [SaiLevel, number][] = [
  ['low', 0],
  ['moderate', 25],
  ['high', 50],
  ['very_high', 75],
]

export function saiLevel(value: number): SaiLevel {
  let level: SaiLevel = 'low'
  for (const [name, lowest] of SAI_LEVELS) if (value >= lowest) level = name
  return level
}

/** The latest run whose window holds the clock. Daily replay runs overlap, so this is the clock's own day. */
export function runForClock(runs: SmokeRunSummary[], clockMs: number): SmokeRunSummary | null {
  let best: SmokeRunSummary | null = null
  for (const run of runs) {
    const start = run.start * 1000
    if (start <= clockMs && clockMs < start + run.hours * HOUR_MS && (best === null || run.start > best.start)) {
      best = run
    }
  }
  return best
}

/** The run after `run` of the same kind, to prefetch while playing. */
export function nextRun(runs: SmokeRunSummary[], run: SmokeRunSummary): SmokeRunSummary | null {
  const later = runs.filter((r) => r.kind === run.kind && r.start > run.start)
  return later.reduce<SmokeRunSummary | null>((best, r) => (best === null || r.start < best.start ? r : best), null)
}

/** Hour of the run the clock is in, clamped to the run. */
export function hourIndex(run: { start: number; hours: number }, clockMs: number): number {
  const hour = Math.floor((clockMs / 1000 - run.start) / 3600)
  return Math.min(run.hours - 1, Math.max(0, hour))
}

/** Unix-second start of a run from its id: a replay day (2025-11-03) or a live run (2026-10-11T1912). */
export function runStartMs(runId: string): number | null {
  const match = /^(\d{4}-\d{2}-\d{2})(?:T(\d{2})(\d{2}))?$/.exec(runId)
  if (!match) return null
  const hour = match[2] === undefined ? 0 : Number(match[2]) + Number(match[3]) / 60
  return istMs(match[1], hour)
}

/** Mean index over all Delhi cells for each hour. */
export function delhiMean(sai: DelhiSai): number[] {
  const series = Object.values(sai.cells)
  return sai.hours.map((_, hour) =>
    series.length === 0 ? 0 : series.reduce((sum, values) => sum + values[hour], 0) / series.length,
  )
}

export interface PeakWindow {
  /** Epoch milliseconds: the first hour at or above the threshold, and the end of the last one. */
  start: number
  end: number
  peak: number
  peakAt: number
  level: SaiLevel
}

/**
 * The stretch of hours around the peak where the index stays at or above half the peak (and at
 * least Moderate). Null when the index never reaches Moderate: no peak worth calling out.
 */
export function peakWindow(hours: number[], sai: number[]): PeakWindow | null {
  if (sai.length === 0) return null
  let top = 0
  for (let i = 1; i < sai.length; i += 1) if (sai[i] > sai[top]) top = i
  const peak = sai[top]
  if (peak < SAI_LEVELS[1][1]) return null
  const threshold = Math.max(SAI_LEVELS[1][1], peak / 2)
  let first = top
  let last = top
  while (first > 0 && sai[first - 1] >= threshold) first -= 1
  while (last < sai.length - 1 && sai[last + 1] >= threshold) last += 1
  return {
    start: hours[first] * 1000,
    end: hours[last] * 1000 + HOUR_MS,
    peak,
    peakAt: hours[top] * 1000,
    level: saiLevel(peak),
  }
}

function fold(text: string): string {
  return text
    .normalize('NFC')
    .toLocaleLowerCase('en-IN')
    .replace(/[\s\-.,']+/g, '')
}

/** Localities whose English or Hindi name contains the query; names that start with it come first. */
export function searchLocalities(items: SmokeLocality[], query: string, limit = 8): SmokeLocality[] {
  const q = fold(query)
  if (q === '') return []
  const scored: [number, SmokeLocality][] = []
  for (const item of items) {
    const names = [fold(item.name), fold(item.name_hi ?? '')].filter((name) => name !== '')
    if (names.some((name) => name.startsWith(q))) scored.push([0, item])
    else if (names.some((name) => name.includes(q))) scored.push([1, item])
  }
  scored.sort((a, b) => a[0] - b[0] || a[1].name.localeCompare(b[1].name))
  return scored.slice(0, limit).map(([, item]) => item)
}

/** The locality to show first: the one named in `preferred` if present, else the one with the highest peak. */
export function defaultLocality(items: SmokeLocality[], preferred: string): SmokeLocality | null {
  const named = items.find((item) => fold(item.name) === fold(preferred))
  if (named) return named
  return items.reduce<SmokeLocality | null>(
    (best, item) => (best === null || Math.max(...item.sai) > Math.max(...best.sai) ? item : best),
    null,
  )
}

/** The locality shown first when nobody has picked one: the brief's example. */
export const PREFERRED_LOCALITY = 'Dwarka'

/** A locality's name in the reader's language, where a Hindi name is known. */
export function placeName(locality: SmokeLocality, language: string): string {
  return language.startsWith('hi') && locality.name_hi ? locality.name_hi : locality.name
}

/** The run whose worst hour has the highest Delhi-wide mean; the earliest of equals. */
export function peakRun(runs: SmokeRunSummary[]): SmokeRunSummary | null {
  return runs.reduce<SmokeRunSummary | null>(
    (best, run) =>
      best === null ||
      run.delhi_mean_peak > best.delhi_mean_peak ||
      (run.delhi_mean_peak === best.delhi_mean_peak && run.start < best.start)
        ? run
        : best,
    null,
  )
}

export interface CityStats {
  /** Mean index over every Delhi cell. */
  mean: number
  /** Cells at High or above, and the number of cells. */
  high: number
  cells: number
}

/** Delhi-wide figures for one hour of a run. */
export function cityStats(sai: DelhiSai, hour: number): CityStats {
  const values = Object.values(sai.cells).map((series) => series[hour] ?? 0)
  const highFrom = SAI_LEVELS[2][1]
  return {
    mean: values.length === 0 ? 0 : values.reduce((sum, value) => sum + value, 0) / values.length,
    high: values.filter((value) => value >= highFrom).length,
    cells: values.length,
  }
}
