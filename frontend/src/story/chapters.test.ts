import { describe, expect, it } from 'vitest'
import { CHAPTERS, dueCues, type Chapter } from './chapters'

const noop = () => undefined
const chapter: Chapter = {
  id: 'pass',
  seconds: 10,
  cues: [
    { at: 0, run: noop },
    { at: 4, run: noop },
    { at: 9, run: noop },
  ],
}

describe('the story', () => {
  it('has five chapters that take about two minutes', () => {
    expect(CHAPTERS.map((c) => c.id)).toEqual(['pass', 'after', 'scars', 'missed', 'smoke'])
    const total = CHAPTERS.reduce((sum, c) => sum + c.seconds, 0)
    expect(total).toBeGreaterThanOrEqual(105)
    expect(total).toBeLessThanOrEqual(130)
  })

  it('starts every chapter with a cue at zero, and keeps cues inside the chapter', () => {
    for (const c of CHAPTERS) {
      expect(c.cues[0].at, c.id).toBe(0)
      for (const cue of c.cues) expect(cue.at, c.id).toBeLessThan(c.seconds)
    }
  })

  it('fires each cue once as the chapter clock passes it', () => {
    expect(dueCues(chapter, -1, 0).map((cue) => cue.at)).toEqual([0])
    expect(dueCues(chapter, 0, 3.9)).toEqual([])
    expect(dueCues(chapter, 3.9, 4.2).map((cue) => cue.at)).toEqual([4])
    expect(dueCues(chapter, 4.2, 4.5)).toEqual([])
    // A long gap (a throttled tab) still fires what it skipped.
    expect(dueCues(chapter, 0, 9.5).map((cue) => cue.at)).toEqual([4, 9])
  })
})
