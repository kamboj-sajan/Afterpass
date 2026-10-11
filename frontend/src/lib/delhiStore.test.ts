import { beforeEach, describe, expect, it } from 'vitest'
import { useDelhi } from './delhiStore'
import { HOUR_MS, istMs } from './time'
import type { SmokeRunSummary } from './types'

const START = istMs('2025-11-06')
const RUN: SmokeRunSummary = {
  run_id: '2025-11-06',
  kind: 'replay',
  start: START / 1000,
  start_ist: '2025-11-06T00:00+05:30',
  hours: 48,
  peak_sai: 100,
  peak_level: 'very_high',
  delhi_mean_peak: 98.9,
  delhi_mean_peak_hour: 0,
  trips: 0,
  trips_mb: 0,
}

describe('Delhi screen state', () => {
  beforeEach(() => {
    useDelhi.setState({ window: null, clockMs: 0, playing: false })
  })

  it('opens a run at its first hour, paused', () => {
    useDelhi.setState({ playing: true })
    useDelhi.getState().openRun(RUN)
    const state = useDelhi.getState()
    expect(state.window).toEqual({ runId: '2025-11-06', start: START, end: START + 48 * HOUR_MS })
    expect(state.clockMs).toBe(START)
    expect(state.playing).toBe(false)
  })

  it('keeps the clock inside the 48 hours', () => {
    useDelhi.getState().openRun(RUN)
    useDelhi.getState().setClock(START - HOUR_MS)
    expect(useDelhi.getState().clockMs).toBe(START)
    useDelhi.getState().setClock(START + 100 * HOUR_MS)
    expect(useDelhi.getState().clockMs).toBe(START + 48 * HOUR_MS - 1)
  })

  it('restarts when play is pressed at the end', () => {
    useDelhi.getState().openRun(RUN)
    useDelhi.getState().setClock(START + 48 * HOUR_MS)
    useDelhi.getState().setPlaying(true)
    expect(useDelhi.getState().clockMs).toBe(START)
    expect(useDelhi.getState().playing).toBe(true)
  })

  it('ignores the clock until a run is open', () => {
    useDelhi.getState().setClock(START)
    expect(useDelhi.getState().clockMs).toBe(0)
  })
})
