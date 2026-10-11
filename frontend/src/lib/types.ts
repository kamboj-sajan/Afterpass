/** Shapes of the public data-contract files written by `afterpass publish`. */

import type { FeatureCollection, MultiPolygon, Polygon } from 'geojson'

export interface Meta {
  generated_at: string
  source_versions: Record<string, unknown>
  demo: boolean
}

export interface Totals {
  burned_ha: number
  recorded_ha: number
  unrecorded_ha: number
  unrecorded_share: number | null
  scar_count: number
}

export interface FirmsCounts {
  firms_count: number
  by_satellite: Record<string, number>
  by_day: Record<string, number>
  by_ist_hour: number[]
}

export interface DayTotals extends Totals {
  first_detected: string
}

export interface WeekTotals extends Totals {
  week: string
}

export interface Pass {
  date: string
  valid_pct: number
  scars: number
  burned_ha: number
}

export interface DistrictSummary extends Totals {
  district: string
  state: string
  cropland_ha: number
  firms: FirmsCounts
  by_day: DayTotals[]
  by_week: WeekTotals[]
  sentinel2: Pass[]
  missing_dates: string[]
}

export interface Summary extends Meta {
  season: number
  window: [string, string]
  totals: Totals
  firms: FirmsCounts
  districts: DistrictSummary[]
  limitations: string[]
}

export interface Latest extends Meta {
  season: number
  run_id: string
  data_through: string
  districts: string[]
}

export interface Items<T> extends Meta {
  items: T[]
}

export interface H3Row {
  h3: string
  week: string
  district: string
  burned_ha: number
  recorded_ha: number
  unrecorded_ha: number
}

export interface FirmsPoint {
  lon: number
  lat: number
  /** IST timestamp, e.g. 2025-11-03T13:35+05:30 */
  ist: string
  sat: string
  conf: string
  frp: number | null
  district: string
}

export interface VillageWeek {
  week: string
  burned_ha: number
  unrecorded_ha: number
}

export interface Village {
  id: string
  name: string
  district: string
  lon: number
  lat: number
  burned_ha: number
  unrecorded_ha: number
  share: number | null
  weekly: VillageWeek[]
}

export interface DistrictProperties extends Totals {
  district: string
  state: string
  cropland_ha: number
  firms_count: number
}

export type DistrictCollection = FeatureCollection<Polygon | MultiPolygon, DistrictProperties> & Meta

export interface ScarProperties {
  scar_id: string
  first_detected: string
  window_start: string
  area_ha: number
  recorded: boolean
  village_id: string
}

export type ScarCollection = FeatureCollection<Polygon | MultiPolygon, ScarProperties> & Meta & { week: string }

export interface ImageryMeta extends Meta {
  village_id: string
  name: string
  district: string
  pre_date: string
  post_date: string
  /** west, south, east, north in degrees */
  bounds: [number, number, number, number]
  size_m: number
  village_unrecorded_ha: number
  window_burned_ha: number
  window_unrecorded_ha: number
  files: { pre_tc: string; post_tc: string; pre_swir: string; post_swir: string }
}

/** One entry of `imagery/index.json`: a village with before/after crops. */
export interface ImageryIndexItem {
  village_id: string
  name: string
  district: string
  pre_date: string
  post_date: string
}

export interface SeasonData {
  latest: Latest
  summary: Summary
  districts: DistrictCollection
  cells: Items<H3Row>
  firms: Items<FirmsPoint>
  villages: Items<Village>
  /** Ids of the villages that have before/after imagery. */
  imagery: Set<string>
}
