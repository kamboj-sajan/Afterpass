import { Wind } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router'
import { Banners } from '@/components/Banners'
import { AskButton, ChatDrawer } from '@/components/ChatDrawer'
import { CommandPalette } from '@/components/CommandPalette'
import { DelhiOutlook } from '@/components/DelhiOutlook'
import { FpsMeter, showFps } from '@/components/FpsMeter'
import { GroundTruthPanel } from '@/components/GroundTruthPanel'
import { ImageryDrawer } from '@/components/ImageryDrawer'
import { MapView } from '@/components/MapView'
import { MissionPanel } from '@/components/MissionPanel'
import { PhoneSheet } from '@/components/PhoneSheet'
import { Timeline } from '@/components/Timeline'
import { DATA_BASE_URL } from '@/lib/config'
import { prefetchSmokeRun, useSeasonData, useSmokeIndex, useSmokeRun } from '@/lib/data'
import { cn } from '@/lib/cn'
import { peakWeek } from '@/lib/metrics'
import { usePlayback } from '@/lib/playback'
import { usePhone } from '@/lib/screen'
import { nextRun, runForClock } from '@/lib/smoke'
import { useExplorer } from '@/lib/store'
import { useStory } from '@/lib/storyStore'
import { HOUR_MS, weekRange } from '@/lib/time'
import type { SeasonData, SmokeRun, SmokeRunSummary } from '@/lib/types'
import { StoryButton, StoryPlayer } from '@/story/StoryPlayer'

/** Start on every published district and the week with the most burned area. */
function useInitialSelection(data: SeasonData | null) {
  useEffect(() => {
    if (data === null || useExplorer.getState().week !== null) return
    const names = data.summary.districts.map((d) => d.district)
    const week = peakWeek(data.summary, names)
    if (week === null) return
    useExplorer.getState().setDistricts(names)
    useExplorer.getState().setWeek(week)
  }, [data])
}

/**
 * `?demo=1` puts the Explorer in the same state every time, for a repeatable recording: the
 * season's biggest week, every district, the clock at noon on its first day. `?story=1` starts
 * the story (brief §13.2).
 */
function useDemoAndStory(data: SeasonData | null) {
  const [params] = useSearchParams()
  const demo = params.get('demo') === '1'
  const story = params.get('story') === '1'
  const done = useRef({ demo: false, story: false })
  useEffect(() => {
    if (data === null) return
    const explorer = useExplorer.getState()
    if (demo && !done.current.demo) {
      done.current.demo = true
      const names = data.summary.districts.map((d) => d.district)
      const week = peakWeek(data.summary, names)
      if (week !== null) {
        explorer.setDistricts(names)
        explorer.setWeek(week)
        explorer.setClock(weekRange(week).start + 12 * HOUR_MS)
        explorer.setSpeed(4)
        explorer.setScope('week')
      }
    }
    if (story && !done.current.story) {
      done.current.story = true
      useStory.getState().start()
    }
    if (!story) done.current.story = false
  }, [data, demo, story])
}

function Loading() {
  const { t } = useTranslation()
  return (
    <div className="absolute inset-0 flex justify-between gap-4 p-4" role="status" aria-label={t('state.loading')}>
      <div className="panel flex w-(--panel-left) flex-col gap-3 p-4">
        <div className="skeleton h-4 w-24" />
        <div className="skeleton h-8" />
        <div className="skeleton h-16" />
        <div className="skeleton h-32" />
      </div>
      <div className="panel flex w-(--panel-right) flex-col gap-3 p-4">
        <div className="skeleton h-4 w-32" />
        <div className="skeleton h-16" />
        <div className="skeleton h-28" />
        <div className="skeleton h-28" />
      </div>
    </div>
  )
}

function LoadError() {
  const { t } = useTranslation()
  return (
    <div className="absolute inset-0 flex items-center justify-center p-6">
      <div className="panel max-w-md p-6" role="alert">
        <h1 className="font-display text-lg font-semibold">{t('state.errorTitle')}</h1>
        <p className="text-text-2 mt-2 text-sm leading-relaxed">{t('state.errorBody', { url: DATA_BASE_URL })}</p>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="focus-ring bg-text text-bg mt-4 cursor-pointer rounded-lg px-3.5 py-2 text-sm font-medium"
        >
          {t('state.retry')}
        </button>
      </div>
    </div>
  )
}

/**
 * The season's smoke run under the clock (one per IST day), loaded as the clock moves. The next
 * day's run is fetched ahead so playback does not wait on it.
 */
function useSmokeForClock(season: number): { run: SmokeRun | null; state: 'none' | 'outside' | 'ready' } {
  const index = useSmokeIndex()
  const runs = useMemo(
    () => (index === null ? [] : index.runs.filter((r) => r.kind === 'replay' && r.run_id.startsWith(`${season}-`))),
    [index, season],
  )
  // A string selector: the Explorer re-renders when the run changes, not on every frame.
  const runId = useExplorer((s) => runForClock(runs, s.clockMs)?.run_id ?? null)
  const summary = runs.find((r) => r.run_id === runId) ?? null
  const run = useSmokeRun(summary)
  useEffect(() => {
    if (summary === null) return
    const next = nextRun(runs, summary)
    if (next !== null) prefetchSmokeRun(next)
  }, [runs, summary])
  if (index === null) return { run: null, state: 'none' }
  if (summary === null || run === null) return { run: null, state: 'outside' }
  return { run, state: 'ready' }
}

const EMPTY_RUNS: SmokeRunSummary[] = []

export function Explorer() {
  const { t } = useTranslation()
  const season = useExplorer((s) => s.season)
  const week = useExplorer((s) => s.week)
  const smokeOn = useExplorer((s) => s.layers.smoke || s.layers.delhi)
  const result = useSeasonData(season)
  const data = result.status === 'ready' ? result.data : null
  useInitialSelection(data)
  useDemoAndStory(data)
  usePlayback()
  const smoke = useSmokeForClock(season)
  const runs = useSmokeIndex()?.runs
  const presenting = useStory((s) => s.presenting)
  const storying = useStory((s) => s.chapter !== null)
  const [outlookOpen, setOutlookOpen] = useState(true)
  const phone = usePhone()

  if (result.status === 'error') return <LoadError />
  if (data === null || week === null) return <Loading />

  if (phone) {
    // Phones: the map fills the screen and the panels live in a bottom sheet (brief §12.2).
    return (
      <main
        id="main"
        className="absolute inset-0 [--edge:8px] [--panel-left:0px] [--panel-right:0px] [--timeline-h:176px]"
      >
        <MapView data={data} smoke={smoke.run} />
        <div className="pointer-events-none absolute inset-x-0 top-0 z-10 flex flex-col gap-2 p-2">
          <StoryPlayer data={data} runs={runs ?? EMPTY_RUNS} />
          <div className="pointer-events-auto">
            <ImageryDrawer data={data} />
          </div>
        </div>
        <PhoneSheet
          title={t('app.name')}
          bar={
            <div className="flex items-stretch gap-2">
              <div className="min-w-0 flex-1">
                <Timeline />
              </div>
              <StoryButton />
              <AskButton />
            </div>
          }
          tabs={[
            { id: 'truth', label: t('truth.title'), content: <GroundTruthPanel data={data} /> },
            {
              id: 'mission',
              label: t('mission.title'),
              content: <MissionPanel data={data} smokeState={smoke.state} />,
            },
            ...(smoke.run !== null && smokeOn
              ? [
                  {
                    id: 'smoke',
                    label: t('layers.smoke.name'),
                    content: <DelhiOutlook run={smoke.run} className="w-full" />,
                  },
                ]
              : []),
          ]}
        />
        <CommandPalette data={data} localities={smoke.run?.localities ?? []} />
        <ChatDrawer screen="map" />
      </main>
    )
  }

  return (
    <main
      id="main"
      className={cn(
        'absolute inset-0',
        presenting && 'presenting',
        // The caption panel sits above the timeline; the map's own controls move up to clear it.
        storying && !presenting && '[--timeline-h:188px]',
      )}
    >
      <MapView data={data} smoke={smoke.run} />
      {/* Panels float over the map; the wrapper ignores the pointer so the map stays draggable. */}
      <div className="pointer-events-none absolute inset-0 grid grid-cols-[auto_minmax(0,1fr)_auto] grid-rows-[minmax(0,1fr)_auto] gap-(--edge) p-(--edge)">
        {/* Presentation mode keeps the content (numbers, images, outlook) and hides the controls. */}
        <div
          className={cn(
            'pointer-events-auto row-span-2 flex min-h-0 flex-col [&>section]:max-h-full',
            presenting && 'invisible',
          )}
        >
          <MissionPanel data={data} smokeState={smoke.state} />
        </div>
        <div className="flex min-h-0 flex-col items-center justify-between gap-3">
          <div className="pointer-events-auto">
            <Banners data={data} />
          </div>
          <div className="flex w-full items-end justify-between gap-3">
            <div className="pointer-events-auto">
              <ImageryDrawer data={data} />
            </div>
            {smoke.run !== null && smokeOn && (
              // Clear of the map's zoom and compass buttons, which sit in this corner.
              <div className="pointer-events-auto mr-11">
                {outlookOpen ? (
                  <DelhiOutlook run={smoke.run} onClose={() => setOutlookOpen(false)} />
                ) : (
                  <button
                    type="button"
                    onClick={() => setOutlookOpen(true)}
                    className="panel focus-ring text-text inline-flex cursor-pointer items-center gap-1.5 px-3 py-2 text-xs font-medium"
                  >
                    <Wind size={14} className="text-smoke" aria-hidden />
                    {t('smoke.open')}
                  </button>
                )}
              </div>
            )}
          </div>
        </div>
        <div className="pointer-events-auto col-start-3 row-span-2 row-start-1 flex min-h-0 flex-col [&>section]:max-h-full">
          <GroundTruthPanel data={data} />
        </div>
        <div className="col-start-2 row-start-2 flex flex-col gap-(--edge)">
          <StoryPlayer data={data} runs={runs ?? EMPTY_RUNS} />
          <div className={cn('pointer-events-auto flex items-stretch gap-(--edge)', presenting && 'hidden')}>
            <div className="min-w-0 flex-1">
              <Timeline />
            </div>
            <StoryButton />
            <AskButton />
          </div>
        </div>
      </div>
      <CommandPalette data={data} localities={smoke.run?.localities ?? []} />
      <ChatDrawer screen="map" />
      {showFps && <FpsMeter />}
    </main>
  )
}
