import { useEffect, useState } from 'react'

/** Frames per second over the last second. Shown only with `?fps=1`, to check the smoke animation. */
export function FpsMeter() {
  const [fps, setFps] = useState<number | null>(null)
  useEffect(() => {
    let frame = 0
    let count = 0
    let since = performance.now()
    const tick = (now: number) => {
      count += 1
      if (now - since >= 1000) {
        setFps(Math.round((count * 1000) / (now - since)))
        count = 0
        since = now
      }
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [])
  return (
    <div
      className="panel tabular text-text pointer-events-none fixed top-2 left-1/2 z-50 -translate-x-1/2 px-2 py-1 text-xs"
      data-testid="fps"
    >
      {fps === null ? '–' : fps} fps
    </div>
  )
}

export const showFps = new URLSearchParams(window.location.search).get('fps') === '1'
