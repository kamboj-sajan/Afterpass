/** The story's playback state and presentation mode (brief §13). */

import { create } from 'zustand'

interface StoryState {
  /** The chapter on screen, or null when the story is not running. */
  chapter: number | null
  paused: boolean
  /** Presentation mode: chrome hidden and captions enlarged, for screen recording. */
  presenting: boolean

  start: () => void
  stop: () => void
  go: (chapter: number) => void
  setPaused: (paused: boolean) => void
  togglePresenting: () => void
}

export const useStory = create<StoryState>((set) => ({
  chapter: null,
  paused: false,
  presenting: false,

  start: () => set({ chapter: 0, paused: false }),
  stop: () => set({ chapter: null, paused: false }),
  go: (chapter) => set({ chapter, paused: false }),
  setPaused: (paused) => set({ paused }),
  togglePresenting: () => set((state) => ({ presenting: !state.presenting })),
}))
