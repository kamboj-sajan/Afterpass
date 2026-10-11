/**
 * The story's embers: glowing dots over the cells that burned, appearing between 15:00 and
 * 19:00 IST. Where they are is real (burned cells of the week). When each appears is an
 * illustration, because the hour a field was lit is not known; the caption says so.
 */

import { ScatterplotLayer } from '@deck.gl/layers'
import { cellToLatLng } from 'h3-js'
import { EMBER, EMBER_CORE, withAlpha } from '@/lib/colors'
import { BURN_WINDOW_HOURS, HOUR_MS, istMs } from '@/lib/time'
import type { BurnCell } from './burns'

export interface Ember {
  position: [number, number]
  /** When in the burn window this ember appears, 0 to 1. */
  appear: number
  hectares: number
}

/** A stable pseudo-random 0-1 for a cell, so the same cell always appears at the same moment. */
function fraction(h3: string): number {
  let hash = 2166136261
  for (let i = 0; i < h3.length; i += 1) hash = Math.imul(hash ^ h3.charCodeAt(i), 16777619)
  return ((hash >>> 0) % 10_000) / 10_000
}

export function prepareEmbers(cells: BurnCell[]): Ember[] {
  return cells
    .filter((cell) => cell.unrecordedHa > 0)
    .map((cell) => {
      const [lat, lng] = cellToLatLng(cell.h3)
      return { position: [lng, lat], appear: fraction(cell.h3), hectares: cell.unrecordedHa }
    })
}

/** Model minutes between redraws: embers bloom over tens of minutes, so this is smooth enough. */
const STEP_MS = 4 * 60 * 1000
const BLOOM_MS = 40 * 60 * 1000

export function embersLayer(options: { data: Ember[]; clockMs: number; day: string | null }) {
  const { data, clockMs, day } = options
  const start = day === null ? 0 : istMs(day, BURN_WINDOW_HOURS[0])
  const span = (BURN_WINDOW_HOURS[1] - BURN_WINDOW_HOURS[0]) * HOUR_MS
  const age = (ember: Ember) => clockMs - (start + ember.appear * span)
  return new ScatterplotLayer<Ember>({
    id: 'story-embers',
    data,
    visible: day !== null && data.length > 0,
    getPosition: (d) => d.position,
    radiusUnits: 'meters',
    radiusMinPixels: 0,
    radiusMaxPixels: 14,
    // An ember flares as it appears, then settles to a size set by the burned hectares.
    getRadius: (d) => {
      const since = age(d)
      if (since < 0) return 0
      return (180 + 26 * Math.sqrt(d.hectares)) * (1 + 1.6 * Math.exp(-since / BLOOM_MS))
    },
    getFillColor: (d) => (age(d) < BLOOM_MS ? withAlpha(EMBER_CORE, 0.95) : withAlpha(EMBER, 0.8)),
    updateTriggers: {
      getRadius: [Math.floor(clockMs / STEP_MS), day],
      getFillColor: [Math.floor(clockMs / STEP_MS), day],
    },
    parameters: { depthCompare: 'always' },
  })
}
