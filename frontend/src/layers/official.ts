/** `official`: NASA FIRMS detections as cyan points (brief §12.4). */

import { DataFilterExtension, type DataFilterExtensionProps } from '@deck.gl/extensions'
import { ScatterplotLayer } from '@deck.gl/layers'
import { INK, OFFICIAL, withAlpha } from '@/lib/colors'
import { HOUR_MS, OVERPASS_HOUR, istMs, istParts, weekDates, weekRange } from '@/lib/time'
import type { FirmsPoint } from '@/lib/types'

export interface OfficialDatum {
  point: FirmsPoint
  /** Minutes after the week's start at which the point becomes visible. */
  revealMinute: number
  /** IST date of the daytime satellite pass that saw it, or null for night detections. */
  passDay: string | null
  /** 0 at the southern edge of the data, 1 at the northern edge. */
  latFraction: number
}

/** The scan line reveals one day's daytime detections from south to north. */
export interface Sweep {
  day: string
  progress: number
}

// Daytime detections come from the passes between about 12:00 and 16:30 IST.
const PASS_HOURS: [number, number] = [12, 16.5]

/** Detections of one week in the chosen districts, with what the time filter needs. */
export function prepareOfficial(points: FirmsPoint[], week: string, districts: string[]): OfficialDatum[] {
  const { start } = weekRange(week)
  const days = new Set(weekDates(week))
  const chosen = points.filter((p) => districts.includes(p.district) && days.has(p.ist.slice(0, 10)))
  const lats = chosen.map((p) => p.lat)
  const south = Math.min(...lats)
  const span = Math.max(...lats) - south || 1
  return chosen.map((point) => {
    const instant = Date.parse(point.ist)
    const { date, hour } = istParts(instant)
    const inPass = hour >= PASS_HOURS[0] && hour < PASS_HOURS[1]
    // Daytime detections all become eligible at the pass time; the scan line then reveals
    // them by latitude. Night detections simply appear at their own time.
    const revealAt = inPass ? istMs(date, OVERPASS_HOUR) : instant
    return {
      point,
      revealMinute: (revealAt - start) / 60_000,
      passDay: inPass ? date : null,
      latFraction: (point.lat - south) / span,
    }
  })
}

const filter = new DataFilterExtension({ filterSize: 2 })

export function officialLayer(options: {
  data: OfficialDatum[]
  clockMs: number
  weekStart: number
  sweep: Sweep | null
  visible: boolean
}) {
  const { data, clockMs, weekStart, sweep, visible } = options
  const clockMinute = (clockMs - weekStart) / 60_000
  return new ScatterplotLayer<OfficialDatum, DataFilterExtensionProps<OfficialDatum>>({
    id: 'official',
    data,
    visible,
    pickable: true,
    getPosition: (d) => [d.point.lon, d.point.lat],
    // Fire radiative power spans two orders of magnitude; a square root keeps dots readable.
    getRadius: (d) => 160 + 70 * Math.sqrt(d.point.frp ?? 1),
    radiusUnits: 'meters',
    radiusMinPixels: 2.5,
    radiusMaxPixels: 16,
    getFillColor: withAlpha(OFFICIAL, 0.95),
    // A dark rim keeps each dot readable on top of the burn columns, which it is drawn over.
    stroked: true,
    getLineColor: withAlpha(INK, 0.9),
    lineWidthMinPixels: 1,
    parameters: { depthCompare: 'always' },
    extensions: [filter],
    getFilterValue: (d) => [d.revealMinute, sweep !== null && d.passDay === sweep.day ? d.latFraction : -1],
    filterRange: [
      // Half a minute of slack: the clock holds exactly on the pass time during a sweep.
      [-1e9, clockMinute + 0.5],
      [-2, sweep === null ? 1 : sweep.progress],
    ],
    updateTriggers: { getFilterValue: sweep?.day ?? '' },
  })
}

/** Milliseconds the clock advances per wall-clock second at 1x: one hour. */
export const CLOCK_RATE_MS = HOUR_MS
