/**
 * Explorer state. The camera and highlight actions mirror the agent's `ui_actions`
 * (brief §10.3), so answers from the chat agent can drive the map through `runUiActions`.
 */

import { create } from 'zustand'
import type { Scope } from './metrics'
import { runStartMs } from './smoke'
import { DAY_MS, HOUR_MS, isoWeekOf, istParts, weekRange } from './time'

export type LayerId = 'official' | 'burns' | 'scars' | 'smoke' | 'delhi' | 'districts'
export type Speed = 1 | 4 | 16

export interface CameraCommand {
  longitude: number
  latitude: number
  zoom: number
  pitch?: number
  bearing?: number
  /** Changes on every command so repeating the same target still moves the camera. */
  nonce: number
}

export type UiAction =
  | { type: 'fly_to'; lon: number; lat: number; zoom: number; pitch?: number; bearing?: number }
  | { type: 'highlight_district'; name: string }
  | { type: 'highlight_village'; id: string }
  | { type: 'show_layer'; id: LayerId }
  | { type: 'open_imagery'; village_id: string }
  | { type: 'play_smoke'; run_id: string; from_hour: number }

interface ExplorerState {
  season: number
  week: string | null
  districts: string[]
  layers: Record<LayerId, boolean>
  scope: Scope
  /** The global clock, epoch milliseconds, always inside the selected week. */
  clockMs: number
  playing: boolean
  speed: Speed
  highlightedDistrict: string | null
  highlightedVillage: string | null
  imageryVillage: string | null
  /** The Delhi locality whose 48-hour outlook is shown. */
  smokeLocality: string | null
  camera: CameraCommand | null
  paletteOpen: boolean

  setWeek: (week: string) => void
  setDistricts: (districts: string[]) => void
  toggleLayer: (id: LayerId) => void
  setScope: (scope: Scope) => void
  setClock: (ms: number) => void
  setPlaying: (playing: boolean) => void
  setSpeed: (speed: Speed) => void
  setPaletteOpen: (open: boolean) => void
  flyTo: (target: Omit<CameraCommand, 'nonce'>) => void
  highlightDistrict: (name: string | null) => void
  highlightVillage: (id: string | null) => void
  showLayer: (id: LayerId) => void
  openImagery: (villageId: string | null) => void
  setSmokeLocality: (id: string | null) => void
  playSmoke: (runId: string, fromHour: number) => void
  runUiActions: (actions: UiAction[]) => void
}

let nonce = 0

export const useExplorer = create<ExplorerState>((set, get) => ({
  season: 2025,
  week: null,
  districts: [],
  layers: { official: true, burns: true, scars: true, smoke: true, delhi: true, districts: true },
  scope: 'week',
  clockMs: 0,
  playing: false,
  speed: 1,
  highlightedDistrict: null,
  highlightedVillage: null,
  imageryVillage: null,
  smokeLocality: null,
  camera: null,
  paletteOpen: false,

  // A newly chosen week starts with its clock at the end, so the whole week is on the map.
  setWeek: (week) => set({ week, clockMs: weekRange(week).end - 1, playing: false }),
  setDistricts: (districts) => set({ districts }),
  toggleLayer: (id) => set((state) => ({ layers: { ...state.layers, [id]: !state.layers[id] } })),
  setScope: (scope) => set({ scope }),
  setClock: (ms) => {
    const { week } = get()
    if (week === null) return
    const { start, end } = weekRange(week)
    set({ clockMs: Math.min(end - 1, Math.max(start, ms)) })
  },
  setPlaying: (playing) => {
    const { week, clockMs } = get()
    if (playing && week !== null) {
      // Pressing play at the end of the week restarts it.
      const { start, end } = weekRange(week)
      if (clockMs >= end - DAY_MS / 24) set({ clockMs: start })
    }
    set({ playing })
  },
  setSpeed: (speed) => set({ speed }),
  setPaletteOpen: (paletteOpen) => set({ paletteOpen }),
  flyTo: (target) => {
    nonce += 1
    set({ camera: { ...target, nonce } })
  },
  highlightDistrict: (highlightedDistrict) => set({ highlightedDistrict }),
  highlightVillage: (highlightedVillage) => set({ highlightedVillage }),
  showLayer: (id) => set((state) => ({ layers: { ...state.layers, [id]: true } })),
  openImagery: (imageryVillage) => set({ imageryVillage }),
  setSmokeLocality: (smokeLocality) => set({ smokeLocality }),
  playSmoke: (runId, fromHour) => {
    const start = runStartMs(runId)
    if (start === null) return
    const at = start + fromHour * HOUR_MS
    const state = get()
    state.setWeek(isoWeekOf(istParts(at).date))
    state.setClock(at)
    set((current) => ({ layers: { ...current.layers, smoke: true, delhi: true } }))
    state.setPlaying(true)
  },
  runUiActions: (actions) => {
    const state = get()
    for (const action of actions) {
      if (action.type === 'fly_to') {
        state.flyTo({
          longitude: action.lon,
          latitude: action.lat,
          zoom: action.zoom,
          pitch: action.pitch,
          bearing: action.bearing,
        })
      } else if (action.type === 'highlight_district') {
        state.highlightDistrict(action.name)
      } else if (action.type === 'highlight_village') {
        state.highlightVillage(action.id)
      } else if (action.type === 'show_layer') {
        state.showLayer(action.id)
      } else if (action.type === 'play_smoke') {
        state.playSmoke(action.run_id, action.from_hour)
      } else {
        state.openImagery(action.village_id)
      }
    }
  },
}))
