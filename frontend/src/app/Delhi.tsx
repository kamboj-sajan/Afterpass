import { useEffect, useLayoutEffect, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useSearchParams } from 'react-router'
import { AskButton, ChatDrawer } from '@/components/ChatDrawer'
import { DelhiMap } from '@/components/DelhiMap'
import { DelhiPanel } from '@/components/DelhiPanel'
import { DelhiTimeline } from '@/components/DelhiTimeline'
import { FpsMeter, showFps } from '@/components/FpsMeter'
import { css, receptorGradient, SMOKE, SMOKE_FRESH } from '@/lib/colors'
import { prefetchSmokeRun, useSmokeIndex, useSmokeRun } from '@/lib/data'
import { useDelhi } from '@/lib/delhiStore'
import { defaultLocality, peakRun, peakWindow, PREFERRED_LOCALITY } from '@/lib/smoke'
import { HOUR_MS } from '@/lib/time'

/** Advances the Delhi clock while playing: one model hour per second at 1x, stopping at the end. */
function useDelhiPlayback() {
  const playing = useDelhi((s) => s.playing)
  const speed = useDelhi((s) => s.speed)
  const runId = useDelhi((s) => s.window?.runId ?? null)
  useEffect(() => {
    if (!playing || runId === null) return
    let frame = 0
    let last = performance.now()
    const tick = (now: number) => {
      const elapsed = Math.min(0.25, (now - last) / 1000) // a background tab must not jump hours
      last = now
      const state = useDelhi.getState()
      if (state.window === null) return
      const after = Math.min(state.window.end - 1, state.clockMs + elapsed * speed * HOUR_MS)
      state.setClock(after)
      if (after >= state.window.end - 1) {
        state.setPlaying(false)
        return
      }
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [playing, speed, runId])
}

function Legend() {
  const { t } = useTranslation()
  return (
    <div className="panel pointer-events-auto flex w-52 flex-col gap-2.5 p-3">
      <div>
        <p className="text-text mb-1.5 text-[11px] font-medium">{t('layers.delhi.name')}</p>
        <div className="h-1.5 rounded-full" style={{ background: receptorGradient() }} />
        <div className="text-text-2 mt-1 flex justify-between text-[10px]">
          <span>{t('legend.saiLow')}</span>
          <span>{t('legend.saiHigh')}</span>
        </div>
      </div>
      <div>
        <p className="text-text mb-1.5 text-[11px] font-medium">{t('layers.smoke.name')}</p>
        <div
          className="h-1.5 rounded-full"
          style={{ background: `linear-gradient(90deg, ${css(SMOKE_FRESH)}, ${css(SMOKE)})` }}
        />
        <div className="text-text-2 mt-1 flex justify-between text-[10px]">
          <span>{t('legend.smokeFresh')}</span>
          <span>{t('legend.smokeOld')}</span>
        </div>
      </div>
    </div>
  )
}

function Waiting(props: { empty: boolean }) {
  const { t } = useTranslation()
  return (
    <div className="absolute inset-0 flex items-center justify-center p-6">
      <div className="panel max-w-md p-6" role="status">
        <h1 className="font-display text-lg font-semibold">{t('delhi.title')}</h1>
        <p className="text-text-2 mt-2 text-sm leading-relaxed">
          {props.empty ? t('legend.smokeMissing') : t('state.loading')}
        </p>
        <Link
          to="/map"
          className="focus-ring text-official mt-3 inline-block text-sm underline-offset-2 hover:underline"
        >
          {t('delhi.back')}
        </Link>
      </div>
    </div>
  )
}

/** Screen C (brief §12.5): Delhi's 48-hour smoke outlook, one replayed day at a time. */
export function Delhi() {
  const index = useSmokeIndex()
  const [params] = useSearchParams()
  const runs = useMemo(
    () => (index === null ? [] : index.runs.filter((r) => r.kind === 'replay').sort((a, b) => a.start - b.start)),
    [index],
  )
  // The run asked for; the one on screen changes only once it has loaded.
  const wantedId = useDelhi((s) => s.wantedRunId)
  const chosenId = wantedId ?? runs.find((r) => r.run_id === params.get('run'))?.run_id ?? peakRun(runs)?.run_id ?? null
  const wanted = runs.find((r) => r.run_id === chosenId) ?? null
  const run = useSmokeRun(wanted)
  const shownId = useDelhi((s) => s.window?.runId ?? null)
  const localityId = useDelhi((s) => s.localityId)

  useLayoutEffect(() => {
    if (run !== null && useDelhi.getState().window?.runId !== run.summary.run_id) {
      useDelhi.getState().openRun(run.summary)
    }
    // A run the assistant asked for starts playing as soon as it is on screen.
    useDelhi.getState().startRequested()
  }, [run])

  // A place named in the link is shown first.
  useEffect(() => {
    const place = params.get('place')
    if (place !== null && useDelhi.getState().localityId === null) useDelhi.getState().setLocality(place)
  }, [params])

  // The neighbouring days load ahead, so stepping does not wait.
  useEffect(() => {
    const position = runs.findIndex((r) => r.run_id === chosenId)
    for (const neighbour of [runs[position - 1], runs[position + 1]]) {
      if (position >= 0 && neighbour !== undefined) prefetchSmokeRun(neighbour)
    }
  }, [runs, chosenId])

  useDelhiPlayback()

  if (run === null || shownId !== run.summary.run_id) return <Waiting empty={index !== null && runs.length === 0} />

  const locality =
    run.localities.find((item) => item.id === localityId) ?? defaultLocality(run.localities, PREFERRED_LOCALITY)
  const peak = locality === null ? null : peakWindow(run.sai.hours, locality.sai)

  return (
    <div
      className="absolute inset-0 [--panel-left:380px] [--panel-right:0px]"
      data-screen="delhi"
      data-testid="delhi-screen"
    >
      <DelhiMap run={run} locality={locality} />
      {/* Panels float over the map; the wrapper ignores the pointer so the map stays draggable. */}
      <div className="pointer-events-none absolute inset-0 grid grid-cols-[auto_minmax(0,1fr)] grid-rows-[minmax(0,1fr)_auto] gap-(--edge) p-(--edge)">
        <div className="pointer-events-auto row-span-2 flex min-h-0 flex-col [&>section]:max-h-full">
          <DelhiPanel
            run={run}
            runs={runs}
            locality={locality}
            onOpen={(next) => useDelhi.getState().wantRun(next.run_id)}
          />
        </div>
        <div className="flex items-start justify-end">
          <Legend />
        </div>
        <div className="pointer-events-auto flex items-stretch gap-(--edge)">
          <div className="min-w-0 flex-1">
            <DelhiTimeline peak={peak} />
          </div>
          <AskButton />
        </div>
      </div>
      <ChatDrawer screen="delhi" />
      {showFps && <FpsMeter />}
    </div>
  )
}
