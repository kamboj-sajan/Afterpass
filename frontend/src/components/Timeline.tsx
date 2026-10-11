import { Pause, Play, Satellite } from 'lucide-react'
import { Slider } from 'radix-ui'
import { useTranslation } from 'react-i18next'
import { css, EMBER, OFFICIAL } from '@/lib/colors'
import { formatDate, formatDateTime } from '@/lib/format'
import { useExplorer, type Speed } from '@/lib/store'
import { BURN_WINDOW_HOURS, DAY_MS, OVERPASS_HOUR, weekDates, weekRange } from '@/lib/time'
import { Segmented } from './ui/Segmented'

const STEP_MS = 10 * 60 * 1000

// The clock changes on every frame of playback, so only these three small pieces read it.

function Playhead(props: { start: number; end: number }) {
  const clockMs = useExplorer((s) => s.clockMs)
  return (
    <div
      className="bg-text pointer-events-none absolute inset-y-0 w-0.5"
      style={{ left: `${((clockMs - props.start) / (props.end - props.start)) * 100}%` }}
    />
  )
}

function Scrubber(props: { start: number; end: number }) {
  const { t, i18n } = useTranslation()
  const clockMs = useExplorer((s) => s.clockMs)
  const setClock = useExplorer((s) => s.setClock)
  const setPlaying = useExplorer((s) => s.setPlaying)
  return (
    <Slider.Root
      min={props.start}
      max={props.end - 1}
      step={STEP_MS}
      value={[clockMs]}
      onValueChange={([value]) => {
        setPlaying(false)
        setClock(value)
      }}
      className="absolute inset-x-0 top-0 flex h-5 touch-none items-center select-none"
    >
      <Slider.Track className="h-5 grow cursor-pointer" />
      <Slider.Thumb
        aria-label={t('timeline.scrub')}
        aria-valuetext={formatDateTime(clockMs, i18n.language)}
        className="focus-ring block h-6 w-2 cursor-grab rounded-sm bg-white shadow"
      />
    </Slider.Root>
  )
}

function ClockText(props: { end: number }) {
  const { i18n } = useTranslation()
  const clockMs = useExplorer((s) => s.clockMs)
  return (
    <div className="tabular text-text text-sm font-semibold" data-testid="clock">
      {formatDateTime(Math.min(clockMs, props.end - DAY_MS / 1440), i18n.language)}
    </div>
  )
}

/** The week as a scrubbable track, with each day's satellite pass and late-afternoon burn window marked. */
export function Timeline() {
  const { t, i18n } = useTranslation()
  const language = i18n.language
  const week = useExplorer((s) => s.week)
  const playing = useExplorer((s) => s.playing)
  const speed = useExplorer((s) => s.speed)
  const setPlaying = useExplorer((s) => s.setPlaying)
  const setSpeed = useExplorer((s) => s.setSpeed)

  if (week === null) return null
  const { start, end } = weekRange(week)
  const dates = weekDates(week)
  const dayPct = 100 / 7

  return (
    <div className="panel flex items-center gap-3 px-3.5 py-2.5 max-md:gap-2 max-md:px-2 md:min-h-(--timeline-h)">
      <button
        type="button"
        aria-label={playing ? t('timeline.pause') : t('timeline.play')}
        title={playing ? t('timeline.pause') : t('timeline.play')}
        onClick={() => setPlaying(!playing)}
        className="focus-ring bg-text text-bg inline-flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-full transition-transform duration-200 hover:scale-105"
      >
        {playing ? <Pause size={16} aria-hidden /> : <Play size={16} className="translate-x-px" aria-hidden />}
      </button>

      <Segmented
        className="max-md:hidden"
        label={t('timeline.speed')}
        value={String(speed)}
        onChange={(value) => setSpeed(Number(value) as Speed)}
        options={[
          { value: '1', label: '1×' },
          { value: '4', label: '4×' },
          { value: '16', label: '16×' },
        ]}
      />

      <div className="min-w-0 flex-1">
        <div className="relative h-9">
          {/* Day cells with the 15:00-19:00 band and the 13:30 pass marker. */}
          <div
            className="border-hairline absolute inset-x-0 top-0 flex h-5 overflow-hidden rounded-md border bg-black/25"
            aria-hidden
          >
            {dates.map((date, index) => (
              <div key={date} className="border-hairline relative h-full flex-1 border-l first:border-l-0">
                <div
                  className="absolute inset-y-0"
                  title={t('timeline.burnWindow')}
                  style={{
                    left: `${(BURN_WINDOW_HOURS[0] / 24) * 100}%`,
                    width: `${((BURN_WINDOW_HOURS[1] - BURN_WINDOW_HOURS[0]) / 24) * 100}%`,
                    background: css(EMBER, 0.22),
                  }}
                />
                <div
                  className="absolute inset-y-0 w-px"
                  title={t('timeline.overpass')}
                  style={{ left: `${(OVERPASS_HOUR / 24) * 100}%`, background: css(OFFICIAL, 0.95) }}
                />
                <span className="text-text-2 absolute top-0.5 left-1 text-[9px] leading-none">
                  {index === 0 || date.endsWith('-01') ? formatDate(date, language) : Number(date.slice(-2))}
                </span>
              </div>
            ))}
            <Playhead start={start} end={end} />
          </div>
          <Scrubber start={start} end={end} />
          <div className="text-text-2 absolute inset-x-0 bottom-0 flex items-center gap-3 text-[10px] max-md:hidden">
            <span className="inline-flex items-center gap-1">
              <Satellite size={11} style={{ color: css(OFFICIAL) }} aria-hidden />
              {t('timeline.overpass')}
            </span>
            <span className="inline-flex items-center gap-1">
              <span className="h-2 w-3 rounded-sm" style={{ background: css(EMBER, 0.4) }} />
              {t('timeline.burnWindow')}
            </span>
          </div>
        </div>
      </div>

      <div className="shrink-0 text-right max-md:hidden" style={{ minWidth: `${dayPct}%` }}>
        <ClockText end={end} />
        <div className="text-text-2 text-[10px] tracking-[0.14em]">{t('timeline.ist')}</div>
      </div>
    </div>
  )
}
