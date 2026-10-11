import { useEffect, useState } from 'react'
import { CLOCK_RATE_MS, type Sweep } from '@/layers/official'
import { useReducedMotion } from './motion'
import { useExplorer } from './store'
import { OVERPASS_HOUR, istMs, istParts, weekRange } from './time'

/** The scan line takes 6 s at 1x and never less than 1.5 s. */
function sweepDurationMs(speed: number): number {
  return Math.max(1500, 6000 / speed)
}

/**
 * Advances the global clock while playing. Each time the clock reaches a day's 13:30 IST
 * satellite pass it holds there while a band sweeps south to north, then carries on.
 * Returns the sweep in progress, if any.
 */
export function usePlayback(): Sweep | null {
  const playing = useExplorer((s) => s.playing)
  const speed = useExplorer((s) => s.speed)
  const week = useExplorer((s) => s.week)
  const reduced = useReducedMotion()
  const [sweep, setSweep] = useState<Sweep | null>(null)

  useEffect(() => {
    if (!playing || week === null) return
    const { end } = weekRange(week)
    let frame = 0
    let last = performance.now()
    let active: { day: string; started: number; duration: number } | null = null

    const tick = (now: number) => {
      const elapsed = Math.min(0.25, (now - last) / 1000) // a background tab must not jump hours
      last = now
      if (active !== null) {
        const progress = (now - active.started) / active.duration
        if (progress >= 1) {
          active = null
          setSweep(null)
        } else {
          setSweep({ day: active.day, progress })
        }
        frame = requestAnimationFrame(tick)
        return
      }

      const state = useExplorer.getState()
      const before = state.clockMs
      let after = Math.min(end - 1, before + elapsed * speed * CLOCK_RATE_MS)
      const day = istParts(after).date
      const pass = istMs(day, OVERPASS_HOUR)
      if (!reduced && before < pass && after >= pass) {
        after = pass
        active = { day, started: now, duration: sweepDurationMs(speed) }
        setSweep({ day, progress: 0 })
      }
      state.setClock(after)
      if (after >= end - 1) {
        state.setPlaying(false)
        return
      }
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => {
      cancelAnimationFrame(frame)
      setSweep(null)
    }
  }, [playing, speed, week, reduced])

  return sweep
}
