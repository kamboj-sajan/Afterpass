/** `smoke`: particle trails from the transport model (brief §8, §12.4), driven by the global clock. */

import { TripsLayer } from '@deck.gl/geo-layers'
import { smokeColor, withAlpha, type RGBA } from '@/lib/colors'
import type { TripsFile } from '@/lib/types'

export interface SmokeTrail {
  path: [number, number][]
  /** Seconds after the run's start: float32 cannot hold unix seconds to the minute. */
  times: number[]
  colors: RGBA[]
}

/** Trails fade over the last six hours of travel. */
export const TRAIL_HOURS = 6
/** Phones draw at most this many trails (brief §12.2: lighter layers on mobile). */
const MOBILE_TRAILS = 5000

/**
 * Trails with times relative to the run start and a colour per vertex: amber when fresh, grey as
 * the smoke ages, and fainter as its weight decays (exp(-age / tau)). Alphas are low because
 * thousands of trails add up: dense smoke should glow, not turn white.
 */
export function prepareSmoke(file: TripsFile, mobile: boolean): SmokeTrail[] {
  const stride = mobile ? Math.max(1, Math.ceil(file.items.length / MOBILE_TRAILS)) : 1
  const tau = file.tau_h * 3600
  const trails: SmokeTrail[] = []
  for (let k = 0; k < file.items.length; k += stride) {
    const trip = file.items[k]
    const first = trip.ts[0]
    trails.push({
      path: trip.path,
      times: trip.ts.map((t) => t - file.start),
      colors: trip.ts.map((t) => {
        const age = trip.age0 + (t - first)
        return withAlpha(smokeColor(age / 3600), 0.05 + 0.25 * Math.exp(-age / tau))
      }),
    })
  }
  return trails
}

export function smokeLayer(options: { data: SmokeTrail[]; runStart: number; clockMs: number; visible: boolean }) {
  const { data, runStart, clockMs, visible } = options
  return new TripsLayer<SmokeTrail>({
    id: 'smoke',
    data,
    visible,
    getPath: (d) => d.path,
    getTimestamps: (d) => d.times,
    getColor: (d) => d.colors,
    widthUnits: 'pixels',
    getWidth: 2,
    widthMinPixels: 2,
    widthMaxPixels: 3,
    // Square caps and joints: rounded ones add triangles to every segment of every trail.
    fadeTrail: true,
    trailLength: TRAIL_HOURS * 3600,
    currentTime: clockMs / 1000 - runStart,
    // Additive blending: where trails overlap, the smoke glows brighter.
    parameters: {
      depthCompare: 'always',
      blend: true,
      blendColorSrcFactor: 'src-alpha',
      blendColorDstFactor: 'one',
      blendAlphaSrcFactor: 'one',
      blendAlphaDstFactor: 'one-minus-src-alpha',
    },
  })
}
