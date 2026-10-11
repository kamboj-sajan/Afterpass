import { beforeEach, describe, expect, it } from 'vitest'
import { useExplorer } from './store'
import { istMs, weekRange } from './time'

const initial = useExplorer.getState()

beforeEach(() => {
  useExplorer.setState(initial, true)
})

describe('explorer store', () => {
  it('puts the clock at the end of a newly chosen week', () => {
    useExplorer.getState().setWeek('2025-W45')
    const { clockMs, playing } = useExplorer.getState()
    expect(clockMs).toBe(weekRange('2025-W45').end - 1)
    expect(playing).toBe(false)
  })

  it('keeps the clock inside the week', () => {
    const { start, end } = weekRange('2025-W45')
    useExplorer.getState().setWeek('2025-W45')
    useExplorer.getState().setClock(start - 1000)
    expect(useExplorer.getState().clockMs).toBe(start)
    useExplorer.getState().setClock(end + 1000)
    expect(useExplorer.getState().clockMs).toBe(end - 1)
  })

  it('restarts the week when play is pressed at its end', () => {
    useExplorer.getState().setWeek('2025-W45')
    useExplorer.getState().setPlaying(true)
    expect(useExplorer.getState().clockMs).toBe(weekRange('2025-W45').start)
    expect(useExplorer.getState().playing).toBe(true)
  })

  it('runs the agent ui_actions', () => {
    useExplorer.setState({ layers: { ...initial.layers, scars: false } })
    useExplorer.getState().runUiActions([
      { type: 'fly_to', lon: 75.9, lat: 30.2, zoom: 12 },
      { type: 'highlight_district', name: 'Sangrur' },
      { type: 'highlight_village', id: 'a' },
      { type: 'show_layer', id: 'scars' },
      { type: 'open_imagery', village_id: 'a' },
    ])
    const state = useExplorer.getState()
    expect(state.camera).toMatchObject({ longitude: 75.9, latitude: 30.2, zoom: 12 })
    expect(state.highlightedDistrict).toBe('Sangrur')
    expect(state.highlightedVillage).toBe('a')
    expect(state.layers.scars).toBe(true)
    expect(state.imageryVillage).toBe('a')
  })

  it('gives every camera command a new nonce', () => {
    const target = { longitude: 75.9, latitude: 30.2, zoom: 12 }
    useExplorer.getState().flyTo(target)
    const first = useExplorer.getState().camera?.nonce
    useExplorer.getState().flyTo(target)
    expect(useExplorer.getState().camera?.nonce).not.toBe(first)
  })

  it('plays a smoke run from an hour, on that week, with the smoke layers on', () => {
    useExplorer.setState({ layers: { ...initial.layers, smoke: false, delhi: false } })
    useExplorer.getState().runUiActions([{ type: 'play_smoke', run_id: '2025-11-03', from_hour: 18 }])
    const state = useExplorer.getState()
    expect(state.week).toBe('2025-W45')
    expect(state.clockMs).toBe(istMs('2025-11-03', 18))
    expect(state.layers.smoke && state.layers.delhi).toBe(true)
    expect(state.playing).toBe(true)
  })
})
