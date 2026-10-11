import { describe, expect, it } from 'vitest'
import { actionTarget, keyNumber, richText, toolDetail } from './agent'
import type { UiAction } from './store'

const fly: UiAction = { type: 'fly_to', lon: 77, lat: 28.6, zoom: 10.5 }
const smoke: UiAction = { type: 'play_smoke', run_id: '2025-11-06', from_hour: 0 }
const locality: UiAction = { type: 'highlight_locality', id: 'x-dwarka' }
const village: UiAction = { type: 'highlight_village', id: 'a-alpha' }

describe('agent replies', () => {
  it('finds the first figure with a unit', () => {
    expect(keyNumber('**1. Chaunda – 850.6 ha not in official counts** (84.8 %)')).toBe('850.6 ha')
    expect(keyNumber('**98.9 % of official fire detections** occur at midday')).toBe('98.9%')
    expect(keyNumber('423,996 hectares burned.')).toBe('423,996 hectares')
    expect(keyNumber('53 619 हेक्टेयर जली')).toBe('53 619 हेक्टेयर')
    expect(keyNumber('I can’t provide that information.')).toBeNull()
  })

  it('names what a tool call was about', () => {
    const use = { name: 'top_unrecorded_villages', ok: true, input: { district: 'Sangrur', season: 2025, n: 10 } }
    expect(toolDetail(use)).toEqual(['Sangrur', '2025'])
    const method = { name: 'method_and_limits', ok: true, input: { topic: 'why_official_counts_miss_fires' } }
    expect(toolDetail(method)).toEqual(['why official counts miss fires'])
  })

  it('reads bold text and list lines, and nothing else', () => {
    const lines = richText('**1. Chaunda – 850.6 ha** (84.8 %)  \n\n- no imagery\n*Data window: 2025.*')
    expect(lines).toHaveLength(3)
    expect(lines[0].marker).toBe('1.')
    expect(lines[0].parts).toEqual([
      { text: 'Chaunda – 850.6 ha', bold: true },
      { text: ' (84.8 %)', bold: false },
    ])
    expect(lines[1]).toEqual({ kind: 'line', marker: '•', parts: [{ text: 'no imagery', bold: false }] })
    expect(lines[2].parts[0].text).toBe('Data window: 2025.')
  })
})

describe('where map actions run', () => {
  it('runs everything on the Explorer when it is open', () => {
    expect(actionTarget([smoke, locality, fly], 'map')).toBe('map')
    expect(actionTarget([], 'map')).toBe('none')
  })

  it('keeps smoke actions on the Delhi screen and sends the rest to the Explorer', () => {
    expect(actionTarget([smoke, locality, fly], 'delhi')).toBe('delhi')
    expect(actionTarget([village, fly], 'delhi')).toBe('map')
    expect(actionTarget([fly], 'delhi')).toBe('map')
    expect(actionTarget([], 'delhi')).toBe('none')
  })
})
