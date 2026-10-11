import { Pause, Play } from 'lucide-react'
import { Slider } from 'radix-ui'
import { useTranslation } from 'react-i18next'
import { css, receptorColor } from '@/lib/colors'
import { useDelhi, type DelhiSpeed } from '@/lib/delhiStore'
import { formatDate, formatDateTime, formatTime } from '@/lib/format'
import type { PeakWindow } from '@/lib/smoke'
import { HOUR_MS, istParts } from '@/lib/time'
import { Segmented } from './ui/Segmented'

const STEP_MS = 10 * 60 * 1000
const TICK_HOURS = 6

// The clock changes on every frame of playback, so only these three small pieces read it.

function Playhead(props: { start: number; end: number }) {
  const clockMs = useDelhi((s) => s.clockMs)
  return (
    <div
      className="bg-text pointer-events-none absolute inset-y-0 w-0.5"
      style={{ left: `${((clockMs - props.start) / (props.end - props.start)) * 100}%` }}
    />
  )
}

function Scrubber(props: { start: number; end: number }) {
  const { t, i18n } = useTranslation()
  const clockMs = useDelhi((s) => s.clockMs)
  const setClock = useDelhi((s) => s.setClock)
  const setPlaying = useDelhi((s) => s.setPlaying)
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
        aria-label={t('delhi.scrub')}
        aria-valuetext={formatDateTime(clockMs, i18n.language)}
        className="focus-ring block h-6 w-2 cursor-grab rounded-sm bg-white shadow"
      />
    </Slider.Root>
  )
}

function ClockText() {
  const { i18n } = useTranslation()
  const clockMs = useDelhi((s) => s.clockMs)
  return (
    <div className="tabular text-text text-sm font-semibold" data-testid="delhi-clock">
      {formatDateTime(clockMs, i18n.language)}
    </div>
  )
}

/** The run's 48 hours as a scrubbable track, with the chosen locality's peak window marked. */
export function DelhiTimeline(props: { peak: PeakWindow | null }) {
  const { t, i18n } = useTranslation()
  const language = i18n.language
  const span = useDelhi((s) => s.window)
  const playing = useDelhi((s) => s.playing)
  const speed = useDelhi((s) => s.speed)
  const setPlaying = useDelhi((s) => s.setPlaying)
  const setSpeed = useDelhi((s) => s.setSpeed)

  if (span === null) return null
  const { start, end } = span
  const pct = (ms: number) => `${((ms - start) / (end - start)) * 100}%`
  const ticks = Array.from(
    { length: (end - start) / (TICK_HOURS * HOUR_MS) },
    (_, i) => start + i * TICK_HOURS * HOUR_MS,
  )

  return (
    <div className="panel flex items-center gap-3 px-3.5 py-2.5 max-md:gap-2 max-md:px-2 md:min-h-(--timeline-h)">
      <button
        type="button"
        aria-label={playing ? t('timeline.pause') : t('delhi.play')}
        title={playing ? t('timeline.pause') : t('delhi.play')}
        onClick={() => setPlaying(!playing)}
        className="focus-ring bg-text text-bg inline-flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-full transition-transform duration-200 hover:scale-105"
      >
        {playing ? <Pause size={16} aria-hidden /> : <Play size={16} className="translate-x-px" aria-hidden />}
      </button>

      <Segmented
        className="max-md:hidden"
        label={t('timeline.speed')}
        value={String(speed)}
        onChange={(value) => setSpeed(Number(value) as DelhiSpeed)}
        options={[
          { value: '1', label: '1×' },
          { value: '4', label: '4×' },
        ]}
      />

      <div className="min-w-0 flex-1">
        <div className="relative h-9">
          <div
            className="border-hairline absolute inset-x-0 top-0 h-5 overflow-hidden rounded-md border bg-black/25"
            aria-hidden
          >
            {props.peak !== null && (
              <div
                className="absolute inset-y-0"
                title={t('delhi.peakBand')}
                style={{
                  left: pct(props.peak.start),
                  width: `${((props.peak.end - props.peak.start) / (end - start)) * 100}%`,
                  background: css(receptorColor(70), 0.4),
                }}
              />
            )}
            {ticks.map((ms, index) => (
              <div
                key={ms}
                className="border-hairline absolute inset-y-0 border-l first:border-l-0"
                style={{ left: pct(ms) }}
              >
                <span className="text-text-2 absolute top-0.5 left-1 text-[9px] leading-none whitespace-nowrap">
                  {/* A forecast starts at the hour it was made, so labels come from the time itself. */}
                  {index === 0 || istParts(ms).hour < TICK_HOURS ? formatDate(ms, language) : formatTime(ms, language)}
                </span>
              </div>
            ))}
            <Playhead start={start} end={end} />
          </div>
          <Scrubber start={start} end={end} />
          <div className="text-text-2 absolute inset-x-0 bottom-0 flex items-center gap-3 text-[10px] max-md:hidden">
            <span className="inline-flex items-center gap-1">
              <span className="h-2 w-3 rounded-sm" style={{ background: css(receptorColor(70), 0.5) }} />
              {t('delhi.peakBand')}
            </span>
          </div>
        </div>
      </div>

      <div className="shrink-0 text-right max-md:hidden">
        <ClockText />
        <div className="text-text-2 text-[10px] tracking-[0.14em]">{t('timeline.ist')}</div>
      </div>
    </div>
  )
}
