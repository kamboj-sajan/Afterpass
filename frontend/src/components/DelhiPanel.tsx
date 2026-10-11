import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useDelhi } from '@/lib/delhiStore'
import { formatDateRange, formatDateTime } from '@/lib/format'
import { cityStats, hourIndex, peakRun } from '@/lib/smoke'
import { HOUR_MS, istParts } from '@/lib/time'
import type { SmokeLocality, SmokeRun, SmokeRunSummary } from '@/lib/types'
import { LevelBadge, LocalityOutlook, LocalitySearch, SaiExplainer, SaiInfo } from './DelhiOutlook'
import { NavLinks } from './NavLinks'
import { NotifyForm } from './NotifyForm'
import { Panel, SectionLabel } from './ui/Panel'
import { Segmented } from './ui/Segmented'

const STEP_BUTTON =
  'focus-ring border-hairline text-text inline-flex size-7 cursor-pointer items-center justify-center rounded-md border hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-40'

/** The districts whose burning a run models, from the provenance its files carry. */
function sourceDistricts(run: SmokeRun): string | null {
  const text = run.sai.source_versions.burn_sources
  if (typeof text !== 'string' || !text.includes(': ')) return null
  return text.slice(text.indexOf(': ') + 2)
}

/** The Delhi screen's panel: which 48 hours, the city this hour, and one locality's outlook. */
export function DelhiPanel(props: {
  run: SmokeRun
  runs: SmokeRunSummary[]
  /** The newest live forecast, if one is published. */
  forecast: SmokeRunSummary | null
  locality: SmokeLocality | null
  onOpen: (run: SmokeRunSummary) => void
}) {
  const { run, runs, forecast, locality } = props
  const live = run.summary.kind === 'live'
  const { t, i18n } = useTranslation()
  const language = i18n.language
  const setLocality = useDelhi((s) => s.setLocality)
  const flyTo = useDelhi((s) => s.flyTo)
  // Re-renders once per model hour, not on every frame of playback.
  const hour = useDelhi((s) => hourIndex(run.summary, s.clockMs))

  const position = runs.findIndex((item) => item.run_id === run.summary.run_id)
  const earlier = position > 0 ? runs[position - 1] : null
  const later = position >= 0 && position < runs.length - 1 ? runs[position + 1] : null
  const peak = peakRun(runs)
  const start = run.summary.start * 1000
  const firstDay = istParts(start).date
  const lastDay = istParts(start + (run.summary.hours - 1) * HOUR_MS).date
  const city = cityStats(run.sai, hour)
  const districts = sourceDistricts(run)

  const pick = (item: SmokeLocality) => {
    setLocality(item.id)
    flyTo({ longitude: item.lon, latitude: item.lat, zoom: 10.8 })
  }

  return (
    <Panel
      title={t('delhi.title')}
      className="w-[min(var(--panel-left),calc(100vw-2*var(--edge)))]"
      actions={
        <div className="flex items-center gap-1">
          <SaiInfo run={run} />
        </div>
      }
    >
      <NavLinks className="px-4 pb-3" />
      <div className="scroll-thin flex min-h-0 flex-col gap-4 overflow-y-auto px-4 pb-4">
        <div>
          <span className="border-hairline text-ember-2 inline-flex rounded-full border px-2 py-0.5 text-[11px] font-medium">
            {run.summary.kind === 'live'
              ? t('delhi.liveBadge')
              : t('delhi.replayBadge', { year: firstDay.slice(0, 4) })}
          </span>
          <p className="text-text-2 mt-2 text-xs leading-snug" data-testid="delhi-sources">
            {districts === null ? t('delhi.sourcesUnnamed') : t('delhi.sources', { districts })}
          </p>
        </div>

        <div>
          <SectionLabel>{t('delhi.window')}</SectionLabel>
          {forecast !== null && peak !== null && (
            <Segmented
              className="mb-2"
              label={t('delhi.window')}
              value={live ? 'live' : 'replay'}
              onChange={(value) => props.onOpen(value === 'live' ? forecast : peak)}
              options={[
                { value: 'live', label: t('delhi.forecast') },
                {
                  value: 'replay',
                  label: t('delhi.replayBadge', { year: istParts(peak.start * 1000).date.slice(0, 4) }),
                },
              ]}
            />
          )}
          {live ? (
            <div data-testid="delhi-window">
              <p className="text-text text-sm font-semibold">
                {t('delhi.forecastFrom', { when: formatDateTime(start, language) })}
              </p>
              <p className="text-text-2 mt-1 text-[11px] leading-snug">{t('smoke.persistence')}</p>
            </div>
          ) : (
            <>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  className={STEP_BUTTON}
                  disabled={earlier === null}
                  onClick={() => earlier && props.onOpen(earlier)}
                  aria-label={t('delhi.previousDay')}
                  title={t('delhi.previousDay')}
                >
                  <ChevronLeft size={15} aria-hidden />
                </button>
                <div className="min-w-0 flex-1 text-center">
                  <p className="text-text text-sm font-semibold" data-testid="delhi-window">
                    {formatDateRange(firstDay, lastDay, language)} {firstDay.slice(0, 4)}
                  </p>
                  <p className="text-text-2 text-[11px]">{t('delhi.windowFrom')}</p>
                </div>
                <button
                  type="button"
                  className={STEP_BUTTON}
                  disabled={later === null}
                  onClick={() => later && props.onOpen(later)}
                  aria-label={t('delhi.nextDay')}
                  title={t('delhi.nextDay')}
                >
                  <ChevronRight size={15} aria-hidden />
                </button>
              </div>
              {peak !== null && peak.run_id !== run.summary.run_id && (
                <button
                  type="button"
                  onClick={() => props.onOpen(peak)}
                  className="focus-ring text-official mt-2 cursor-pointer text-xs underline-offset-2 hover:underline"
                >
                  {t('delhi.seasonPeak')}
                </button>
              )}
            </>
          )}
        </div>

        <div className="grid grid-cols-2 gap-2">
          <div className="border-hairline rounded-xl border bg-black/20 p-2.5">
            <p className="text-text-2 mb-1.5 text-[11px]">{t('delhi.cityNow')}</p>
            <span data-testid="delhi-mean">
              <LevelBadge value={city.mean} />
            </span>
          </div>
          <div className="border-hairline rounded-xl border bg-black/20 p-2.5">
            <p className="text-text-2 mb-1 text-[11px]">{t('delhi.cellsHigh')}</p>
            <p className="tabular text-text text-sm font-semibold" data-testid="delhi-high">
              {t('delhi.cellsOf', { count: city.high, total: city.cells })}
            </p>
          </div>
        </div>

        <div className="flex flex-col gap-2.5">
          <SectionLabel>{t('delhi.locality')}</SectionLabel>
          <LocalitySearch items={run.localities} onPick={pick} />
          {locality === null ? (
            <p className="text-text-2 text-xs">{t('smoke.noLocalities')}</p>
          ) : (
            <LocalityOutlook run={run} locality={locality} hour={hour} chartHeight={170} />
          )}
        </div>

        <NotifyForm zone={locality?.district ?? null} />

        <SaiExplainer />
        <p className="text-text-2 text-[10px]">{t('credits.winds')}</p>
      </div>
    </Panel>
  )
}
