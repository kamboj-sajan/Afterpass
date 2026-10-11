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
  /** The run to show, chosen with the day stepper or asked for by the assistant. */
  wantedRunId: string | null
  /** A run the assistant asked to play; it starts once it is on screen. */
  request: { runId: string; fromHour: number } | null

  openRun: (run: SmokeRunSummary) => void
  setClock: (ms: number) => void
  setPlaying: (playing: boolean) => void
  setSpeed: (speed: DelhiSpeed) => void
  setLocality: (id: string | null) => void
  flyTo: (target: Omit<CameraCommand, 'nonce'>) => void
  wantRun: (runId: string) => void
  requestRun: (runId: string, fromHour: number) => void
  /** Starts a requested run if it is the one on screen. */
  startRequested: () => void
}

let nonce = 0

export const useDelhi = create<DelhiState>((set, get) => ({
  window: null,
  clockMs: 0,
  playing: false,
  speed: 1,
  localityId: null,
  camera: null,
  wantedRunId: null,
  request: null,

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
  wantRun: (wantedRunId) => set({ wantedRunId }),
  requestRun: (runId, fromHour) => {
    set({ wantedRunId: runId, request: { runId, fromHour } })
    get().startRequested()
  },
  startRequested: () => {
    const { request, window } = get()
    if (request === null || window === null || window.runId !== request.runId) return
    const at = Math.min(window.end - 1, Math.max(window.start, window.start + request.fromHour * HOUR_MS))
    set({ request: null, clockMs: at, playing: true })
  },
}))
