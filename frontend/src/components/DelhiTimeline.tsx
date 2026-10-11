import { Pause, Play } from 'lucide-react'
import { Slider } from 'radix-ui'
import { useTranslation } from 'react-i18next'
import { css, receptorColor } from '@/lib/colors'
import { useDelhi, type DelhiSpeed } from '@/lib/delhiStore'
import { formatDate, formatDateTime } from '@/lib/format'
import type { PeakWindow } from '@/lib/smoke'
import { HOUR_MS } from '@/lib/time'
import { Segmented } from './ui/Segmented'

const STEP_MS = 10 * 60 * 1000
const TICK_HOURS = 6

/** The run's 48 hours as a scrubbable track, with the chosen locality's peak window marked. */
export function DelhiTimeline(props: { peak: PeakWindow | null }) {
  const { t, i18n } = useTranslation()
  const language = i18n.language
  const span = useDelhi((s) => s.window)
  const clockMs = useDelhi((s) => s.clockMs)
  const playing = useDelhi((s) => s.playing)
  const speed = useDelhi((s) => s.speed)
  const setClock = useDelhi((s) => s.setClock)
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
    <div className="panel flex min-h-(--timeline-h) items-center gap-3 px-3.5 py-2.5">
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
                  {index % 4 === 0
                    ? formatDate(ms, language)
                    : `${String((index * TICK_HOURS) % 24).padStart(2, '0')}:00`}
                </span>
              </div>
            ))}
            <div className="bg-text pointer-events-none absolute inset-y-0 w-0.5" style={{ left: pct(clockMs) }} />
          </div>
          <Slider.Root
            min={start}
            max={end - 1}
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
              aria-valuetext={formatDateTime(clockMs, language)}
              className="focus-ring block h-6 w-2 cursor-grab rounded-sm bg-white shadow"
            />
          </Slider.Root>
          <div className="text-text-2 absolute inset-x-0 bottom-0 flex items-center gap-3 text-[10px]">
            <span className="inline-flex items-center gap-1">
              <span className="h-2 w-3 rounded-sm" style={{ background: css(receptorColor(70), 0.5) }} />
              {t('delhi.peakBand')}
            </span>
          </div>
        </div>
      </div>

      <div className="shrink-0 text-right">
        <div className="tabular text-text text-sm font-semibold" data-testid="delhi-clock">
          {formatDateTime(clockMs, language)}
        </div>
        <div className="text-text-2 text-[10px] tracking-[0.14em]">{t('timeline.ist')}</div>
      </div>
    </div>
  )
}
