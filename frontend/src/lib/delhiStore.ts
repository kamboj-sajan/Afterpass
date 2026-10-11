/** State of the Delhi screen: one 48-hour smoke run, its own clock and the chosen locality. */

import { create } from 'zustand'
import type { CameraCommand } from './store'
import { HOUR_MS } from './time'
import type { SmokeRunSummary } from './types'

export type DelhiSpeed = 1 | 4

/** The run on screen and the span of its clock, in epoch milliseconds. */
export interface DelhiWindow {
  runId: string
  start: number
  end: number
}

interface DelhiState {
  window: DelhiWindow | null
  clockMs: number
  playing: boolean
  speed: DelhiSpeed
  localityId: string | null
  camera: CameraCommand | null

  openRun: (run: SmokeRunSummary) => void
  setClock: (ms: number) => void
  setPlaying: (playing: boolean) => void
  setSpeed: (speed: DelhiSpeed) => void
  setLocality: (id: string | null) => void
  flyTo: (target: Omit<CameraCommand, 'nonce'>) => void
}

let nonce = 0

export const useDelhi = create<DelhiState>((set, get) => ({
  window: null,
  clockMs: 0,
  playing: false,
  speed: 1,
  localityId: null,
  camera: null,

  // A newly opened run starts at its first hour.
  openRun: (run) => {
    const start = run.start * 1000
    set({ window: { runId: run.run_id, start, end: start + run.hours * HOUR_MS }, clockMs: start, playing: false })
  },
  setClock: (ms) => {
    const { window } = get()
    if (window === null) return
    set({ clockMs: Math.min(window.end - 1, Math.max(window.start, ms)) })
  },
  setPlaying: (playing) => {
    const { window, clockMs } = get()
    // Pressing play at the end of the 48 hours restarts them.
    if (playing && window !== null && clockMs >= window.end - HOUR_MS) set({ clockMs: window.start })
    set({ playing })
  },
  setSpeed: (speed) => set({ speed }),
  setLocality: (localityId) => set({ localityId }),
  flyTo: (target) => {
    nonce += 1
    set({ camera: { ...target, nonce } })
  },
}))
