import { Wind } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Banners } from '@/components/Banners'
import { CommandPalette } from '@/components/CommandPalette'
import { DelhiOutlook } from '@/components/DelhiOutlook'
import { GroundTruthPanel } from '@/components/GroundTruthPanel'
import { ImageryDrawer } from '@/components/ImageryDrawer'
import { MapView } from '@/components/MapView'
import { MissionPanel } from '@/components/MissionPanel'
import { Timeline } from '@/components/Timeline'
import { DATA_BASE_URL } from '@/lib/config'
import { prefetchSmokeRun, useSeasonData, useSmokeIndex, useSmokeRun } from '@/lib/data'
import { weeklySeries } from '@/lib/metrics'
import { usePlayback } from '@/lib/playback'
import { nextRun, runForClock } from '@/lib/smoke'
import { useExplorer } from '@/lib/store'
import type { SeasonData, SmokeRun } from '@/lib/types'

/** Start on every published district and the week with the most burned area. */
function useInitialSelection(data: SeasonData | null) {
  useEffect(() => {
    if (data === null || useExplorer.getState().week !== null) return
    const names = data.summary.districts.map((d) => d.district)
    const series = weeklySeries(data.summary, names)
    if (series.length === 0) return
    const peak = series.reduce((best, row) =>
      row.recorded_ha + row.unrecorded_ha > best.recorded_ha + best.unrecorded_ha ? row : best,
    )
    useExplorer.getState().setDistricts(names)
    useExplorer.getState().setWeek(peak.week)
  }, [data])
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

export function Explorer() {
  const { t } = useTranslation()
  const season = useExplorer((s) => s.season)
  const week = useExplorer((s) => s.week)
  const smokeOn = useExplorer((s) => s.layers.smoke || s.layers.delhi)
  const result = useSeasonData(season)
  const data = result.status === 'ready' ? result.data : null
  useInitialSelection(data)
  const sweep = usePlayback()
  const smoke = useSmokeForClock(season)
  const [outlookOpen, setOutlookOpen] = useState(true)

  if (result.status === 'error') return <LoadError />
  if (data === null || week === null) return <Loading />

  return (
    <div className="absolute inset-0">
      <MapView data={data} sweep={sweep} smoke={smoke.run} />
      {/* Panels float over the map; the wrapper ignores the pointer so the map stays draggable. */}
      <div className="pointer-events-none absolute inset-0 grid grid-cols-[auto_minmax(0,1fr)_auto] grid-rows-[minmax(0,1fr)_auto] gap-(--edge) p-(--edge)">
        <div className="pointer-events-auto row-span-2 flex min-h-0 flex-col [&>section]:max-h-full">
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
              <div className="pointer-events-auto">
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
        <div className="pointer-events-auto col-start-2 row-start-2">
          <Timeline />
        </div>
      </div>
      <CommandPalette data={data} localities={smoke.run?.localities ?? []} />
    </div>
  )
}
