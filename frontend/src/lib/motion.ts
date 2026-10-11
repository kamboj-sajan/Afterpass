import { useEffect, useState, useSyncExternalStore } from 'react'

const QUERY = '(prefers-reduced-motion: reduce)'

function subscribe(onChange: () => void): () => void {
  const media = window.matchMedia(QUERY)
  media.addEventListener('change', onChange)
  return () => media.removeEventListener('change', onChange)
}

/** True when the visitor asked for less motion: no count-ups, sweeps or camera flights. */
export function useReducedMotion(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => window.matchMedia(QUERY).matches,
    () => false,
  )
}

/**
 * Animate from the previous value to `target` over `durationMs` with an ease-out curve.
 * With reduced motion the value changes at once.
 */
export function useAnimatedNumber(target: number, durationMs: number): number {
  const reduced = useReducedMotion()
  const [value, setValue] = useState(target)
  useEffect(() => {
    if (reduced) return
    let frame = 0
    let from: number | null = null
    const started = performance.now()
    const tick = (now: number) => {
      const progress = Math.min(1, (now - started) / durationMs)
      const eased = 1 - (1 - progress) ** 3
      setValue((current) => {
        if (from === null) from = current
        return from + (target - from) * eased
      })
      if (progress < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [target, durationMs, reduced])
  return reduced ? target : value
}

/** Goes 0 → 1 over `durationMs` every time `key` changes. Used to raise the H3 columns. */
export function useRise(key: string, durationMs: number): number {
  const reduced = useReducedMotion()
  const [state, setState] = useState({ key, progress: 0 })
  useEffect(() => {
    if (reduced) return
    let frame = 0
    const started = performance.now()
    const tick = (now: number) => {
      const progress = Math.min(1, (now - started) / durationMs)
      setState({ key, progress: 1 - (1 - progress) ** 3 })
      if (progress < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [key, durationMs, reduced])
  if (reduced) return 1
  return state.key === key ? state.progress : 0
}
