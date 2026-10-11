import { ExternalLink, Maximize2, Search, Wind, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { SmokeOutlookChart } from '@/charts/SmokeOutlook'
import { cn } from '@/lib/cn'
import { css, receptorColor } from '@/lib/colors'
import { formatDateTime, formatTime } from '@/lib/format'
import {
  defaultLocality,
  hourIndex,
  peakWindow,
  placeName,
  PREFERRED_LOCALITY,
  saiLevel,
  searchLocalities,
} from '@/lib/smoke'
import { useExplorer } from '@/lib/store'
import { istParts } from '@/lib/time'
import type { SmokeLocality, SmokeRun } from '@/lib/types'
import { InfoPopover } from './ui/InfoPopover'

/** CPCB's national AQI portal, for anyone making a health decision. */
const OFFICIAL_AQI = 'https://airquality.cpcb.gov.in/AQI_India/'

export function LevelBadge(props: { value: number }) {
  const { t } = useTranslation()
  const colour = receptorColor(props.value)
  return (
    <span
      className="tabular inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium"
      style={{ borderColor: css(colour, 0.6), background: css(colour, 0.14), color: css(colour) }}
    >
      <span className="size-1.5 rounded-full" style={{ background: css(colour) }} aria-hidden />
      {t(`smoke.level.${saiLevel(props.value)}`)} · {Math.round(props.value)}
    </span>
  )
}

export function LocalitySearch(props: { items: SmokeLocality[]; onPick: (item: SmokeLocality) => void }) {
  const { t, i18n } = useTranslation()
  const [query, setQuery] = useState('')
  const results = useMemo(() => searchLocalities(props.items, query), [props.items, query])
  return (
    <div className="relative">
      <label className="border-hairline flex items-center gap-2 rounded-lg border bg-black/25 px-2.5 py-1.5">
        <Search size={13} className="text-text-2 shrink-0" aria-hidden />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={t('smoke.search')}
          aria-label={t('smoke.search')}
          className="text-text placeholder:text-text-2 w-full bg-transparent text-xs outline-none"
        />
      </label>
      {results.length > 0 && (
        <ul className="panel absolute inset-x-0 top-full z-20 mt-1 max-h-48 overflow-y-auto p-1" role="listbox">
          {results.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                onClick={() => {
                  props.onPick(item)
                  setQuery('')
                }}
                className="focus-ring text-text flex w-full cursor-pointer items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left text-xs hover:bg-white/10"
              >
                <span className="truncate">{placeName(item, i18n.language)}</span>
                <span className="text-text-2 shrink-0 text-[10px]">{item.district}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/** One locality's name, level at the clock's hour, 48-hour chart and peak window. */
export function LocalityOutlook(props: {
  run: SmokeRun
  locality: SmokeLocality
  /** The run's hour under the clock, or null when the clock is outside the run. */
  hour: number | null
  chartHeight?: number
}) {
  const { run, locality, hour } = props
  const { t, i18n } = useTranslation()
  const language = i18n.language
  const peak = peakWindow(run.sai.hours, locality.sai)
  return (
    <>
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="text-text truncate text-sm font-semibold" data-testid="smoke-locality">
            {placeName(locality, language)}
          </p>
          <p className="text-text-2 text-[11px]">{locality.district}</p>
        </div>
        {hour !== null && (
          <div className="text-right">
            <p className="text-text-2 mb-0.5 text-[10px] tracking-[0.12em] uppercase">{t('smoke.now')}</p>
            <LevelBadge value={locality.sai[hour]} />
          </div>
        )}
      </div>
      <SmokeOutlookChart
        hours={run.sai.hours}
        sai={locality.sai}
        nowMs={hour === null ? null : run.sai.hours[hour] * 1000}
        peak={peak}
        height={props.chartHeight}
      />
      <p className="text-text text-xs" data-testid="smoke-peak">
        {peak === null
          ? t('smoke.noPeak')
          : t('smoke.peak', {
              from: formatDateTime(peak.start, language),
              // The date is said once when the window ends on the day it began.
              to:
                istParts(peak.start).date === istParts(peak.end).date
                  ? formatTime(peak.end, language)
                  : formatDateTime(peak.end, language),
              level: t(`smoke.level.${peak.level}`),
            })}
      </p>
    </>
  )
}

/** One sentence on what the index is, with a link to official AQI (brief §12.5). */
export function SaiExplainer() {
  const { t } = useTranslation()
  return (
    <p className="text-text-2 text-[11px] leading-snug">
      {t('smoke.explain')}{' '}
      <a
        href={OFFICIAL_AQI}
        target="_blank"
        rel="noreferrer"
        className="focus-ring text-official inline-flex items-center gap-0.5 underline-offset-2 hover:underline"
      >
        {t('smoke.officialAqi')}
        <ExternalLink size={10} aria-hidden />
      </a>
    </p>
  )
}

/** What the index is and where this run's numbers come from. */
export function SaiInfo(props: { run: SmokeRun }) {
  const { run } = props
  const { t, i18n } = useTranslation()
  return (
    <InfoPopover label={t('smoke.about')}>
      <p className="text-text mb-1 font-medium">{t('smoke.about')}</p>
      <p>{t('smoke.method')}</p>
      {run.summary.kind === 'live' && <p className="text-ember-2 mt-1.5">{t('smoke.persistence')}</p>}
      <p className="text-text mt-2 mb-1 font-medium">{t('kpi.source')}</p>
      <p className="font-mono break-all">smoke/{run.summary.run_id}/localities.json</p>
      <p className="mt-1">
        {t('kpi.generated', { when: formatDateTime(Date.parse(run.sai.generated_at), i18n.language) })}
      </p>
      <p className="mt-1">{t('credits.winds')}</p>
    </InfoPopover>
  )
}

/** The 48-hour smoke outlook card in the Explorer (brief §12.4), following the global clock. */
export function DelhiOutlook(props: { run: SmokeRun; className?: string; onClose?: () => void }) {
  const { run } = props
  const { t, i18n } = useTranslation()
  const language = i18n.language
  const selectedId = useExplorer((s) => s.smokeLocality)
  const setLocality = useExplorer((s) => s.setSmokeLocality)
  const flyTo = useExplorer((s) => s.flyTo)
  // Re-renders once per model hour, not on every frame of playback.
  const hour = useExplorer((s) => {
    const index = hourIndex(run.summary, s.clockMs)
    const start = run.summary.start * 1000
    return s.clockMs >= start && s.clockMs < start + run.summary.hours * 3_600_000 ? index : null
  })

  const locality =
    run.localities.find((item) => item.id === selectedId) ?? defaultLocality(run.localities, PREFERRED_LOCALITY)
  const live = run.summary.kind === 'live'
  const fullView = `/delhi?run=${run.summary.run_id}${locality === null ? '' : `&place=${encodeURIComponent(locality.id)}`}`

  const pick = (item: SmokeLocality) => {
    setLocality(item.id)
    flyTo({ longitude: item.lon, latitude: item.lat, zoom: 10.5 })
  }

  return (
    <section
      className={cn('panel flex w-[min(380px,calc(100vw-2rem))] flex-col gap-2.5 p-3.5', props.className)}
      aria-label={t('smoke.title')}
      data-testid="delhi-outlook"
    >
      <header className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="font-display text-text flex items-center gap-1.5 text-sm font-semibold tracking-[0.1em] uppercase">
            <Wind size={14} className="text-smoke" aria-hidden />
            {t('smoke.title')}
          </h2>
          <p className="text-text-2 text-[11px]">
            {t(live ? 'smoke.fromLive' : 'smoke.fromReplay', {
              when: formatDateTime(run.summary.start * 1000, language),
            })}
          </p>
        </div>
        <div className="flex items-center gap-1">
          <SaiInfo run={run} />
          <Link
            to={fullView}
            aria-label={t('delhi.open')}
            title={t('delhi.open')}
            className="focus-ring text-text-2 inline-flex size-6 items-center justify-center rounded-md hover:text-white"
          >
            <Maximize2 size={13} aria-hidden />
          </Link>
          {props.onClose && (
            <button
              type="button"
              onClick={props.onClose}
              aria-label={t('smoke.close')}
              className="focus-ring text-text-2 inline-flex size-6 cursor-pointer items-center justify-center rounded-md hover:text-white"
            >
              <X size={14} aria-hidden />
            </button>
          )}
        </div>
      </header>

      <LocalitySearch items={run.localities} onPick={pick} />

      {locality === null ? (
        <p className="text-text-2 text-xs">{t('smoke.noLocalities')}</p>
      ) : (
        <LocalityOutlook run={run} locality={locality} hour={hour} />
      )}

      <SaiExplainer />
    </section>
  )
}
