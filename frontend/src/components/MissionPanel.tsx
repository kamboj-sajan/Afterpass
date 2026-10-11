import { memo } from 'react'
import { Search } from 'lucide-react'
import { Slider } from 'radix-ui'
import { useTranslation } from 'react-i18next'
import { css, EMBER, OFFICIAL, receptorGradient, shareGradient, SMOKE, SMOKE_FRESH } from '@/lib/colors'
import { SCAR_MIN_ZOOM, usingAmazonLocation } from '@/lib/config'
import { formatDate, formatDateRange } from '@/lib/format'
import { seasonWeeks } from '@/lib/metrics'
import { useExplorer, type LayerId } from '@/lib/store'
import { weekDates } from '@/lib/time'
import type { SeasonData } from '@/lib/types'
import { NavLinks } from './NavLinks'
import { InfoPopover } from './ui/InfoPopover'
import { Panel, SectionLabel } from './ui/Panel'
import { Segmented } from './ui/Segmented'
import { Switch } from './ui/Switch'

function LayerLegend(props: { id: LayerId }) {
  const { t } = useTranslation()
  if (props.id === 'burns') {
    return (
      <div className="mt-1.5">
        <div className="h-1.5 rounded-full" style={{ background: shareGradient() }} />
        <div className="text-text-2 mt-1 flex justify-between text-[10px]">
          <span>{t('legend.allRecorded')}</span>
          <span>{t('legend.noneRecorded')}</span>
        </div>
      </div>
    )
  }
  if (props.id === 'smoke') {
    return (
      <div className="mt-1.5">
        <div
          className="h-1.5 rounded-full"
          style={{ background: `linear-gradient(90deg, ${css(SMOKE_FRESH)}, ${css(SMOKE)})` }}
        />
        <div className="text-text-2 mt-1 flex justify-between text-[10px]">
          <span>{t('legend.smokeFresh')}</span>
          <span>{t('legend.smokeOld')}</span>
        </div>
      </div>
    )
  }
  if (props.id === 'delhi') {
    return (
      <div className="mt-1.5">
        <div className="h-1.5 rounded-full" style={{ background: receptorGradient() }} />
        <div className="text-text-2 mt-1 flex justify-between text-[10px]">
          <span>{t('legend.saiLow')}</span>
          <span>{t('legend.saiHigh')}</span>
        </div>
      </div>
    )
  }
  if (props.id === 'scars') {
    return (
      <div className="text-text-2 mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-[10px]">
        <span className="inline-flex items-center gap-1.5">
          <span
            className="size-2.5 rounded-sm"
            style={{ background: css(EMBER, 0.45), border: `1px solid ${css(EMBER)}` }}
          />
          {t('legend.unrecordedScar')}
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="size-2.5 rounded-sm" style={{ border: `1px solid ${css(OFFICIAL)}` }} />
          {t('legend.recordedScar')}
        </span>
      </div>
    )
  }
  return null
}

/** Layers that need a published smoke run. */
const SMOKE_LAYERS: LayerId[] = ['smoke', 'delhi']

export const MissionPanel = memo(function MissionPanel(props: {
  data: SeasonData
  smokeState: 'none' | 'outside' | 'ready'
}) {
  const { data, smokeState } = props
  const { t, i18n } = useTranslation()
  const language = i18n.language
  const season = useExplorer((s) => s.season)
  const week = useExplorer((s) => s.week)
  const districts = useExplorer((s) => s.districts)
  const layers = useExplorer((s) => s.layers)
  const setWeek = useExplorer((s) => s.setWeek)
  const setDistricts = useExplorer((s) => s.setDistricts)
  const toggleLayer = useExplorer((s) => s.toggleLayer)
  const setPaletteOpen = useExplorer((s) => s.setPaletteOpen)

  const weeks = seasonWeeks(data.summary)
  const weekIndex = week === null ? 0 : Math.max(0, weeks.indexOf(week))
  const dates = week === null ? null : weekDates(week)
  const accents: Record<LayerId, 'official' | 'ember' | 'neutral'> = {
    official: 'official',
    burns: 'ember',
    scars: 'ember',
    smoke: 'neutral',
    delhi: 'ember',
    districts: 'neutral',
  }

  return (
    <Panel
      title={t('mission.title')}
      className="w-(--panel-left)"
      actions={
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setPaletteOpen(true)}
            className="focus-ring text-text-2 border-hairline inline-flex cursor-pointer items-center gap-1.5 rounded-md border px-1.5 py-1 text-[11px] hover:text-white"
          >
            <Search size={12} aria-hidden />
            {t('mission.search')}
            <kbd className="font-mono text-[10px] opacity-70">⌘K</kbd>
          </button>
        </div>
      }
    >
      <NavLinks className="px-4 pb-3" />
      <div className="scroll-thin flex min-h-0 flex-col gap-4 overflow-y-auto px-4 pb-4">
        <div>
          <SectionLabel>{t('mission.season')}</SectionLabel>
          <Segmented
            label={t('mission.season')}
            value={String(season)}
            onChange={() => undefined}
            options={[
              { value: '2025', label: t('mission.replay', { year: 2025 }) },
              {
                value: '2026',
                label: t('mission.live', { year: 2026 }),
                disabled: true,
                title: t('mission.liveUnavailable'),
              },
            ]}
          />
          <p className="text-text-2 mt-1.5 text-[11px]">
            {t('mission.dataThrough', { date: formatDate(data.latest.data_through, language, true) })}
          </p>
        </div>

        <div>
          <SectionLabel>{t('mission.week')}</SectionLabel>
          <p className="text-text text-xs font-medium" data-testid="week-label">
            {week !== null && dates !== null
              ? t('mission.weekLabel', {
                  number: Number(week.slice(-2)),
                  range: formatDateRange(dates[0], dates[6], language),
                })
              : '–'}
          </p>
          <Slider.Root
            min={0}
            max={Math.max(0, weeks.length - 1)}
            step={1}
            value={[weekIndex]}
            onValueChange={([index]) => setWeek(weeks[index])}
            className="relative mt-2 flex h-5 w-full touch-none items-center select-none"
          >
            <Slider.Track className="relative h-1 grow rounded-full bg-white/12">
              <Slider.Range className="bg-ember/80 absolute h-full rounded-full" />
            </Slider.Track>
            <Slider.Thumb
              aria-label={t('mission.week')}
              className="focus-ring bg-text block size-4 cursor-grab rounded-full shadow"
            />
          </Slider.Root>
          <div className="text-text-2 tabular mt-0.5 flex justify-between px-1.5 text-[9px]" aria-hidden>
            {weeks.map((label) => (
              <span key={label} className={label === week ? 'text-text' : undefined}>
                {Number(label.slice(-2))}
              </span>
            ))}
          </div>
        </div>

        <div>
          <SectionLabel>{t('mission.districts')}</SectionLabel>
          <div className="flex flex-wrap gap-1.5">
            {data.summary.districts.map((district) => {
              const on = districts.includes(district.district)
              return (
                <button
                  key={district.district}
                  type="button"
                  aria-pressed={on}
                  onClick={() =>
                    setDistricts(
                      on ? districts.filter((name) => name !== district.district) : [...districts, district.district],
                    )
                  }
                  className={
                    'focus-ring cursor-pointer rounded-full border px-2.5 py-1 text-xs transition-colors duration-200 ' +
                    (on ? 'border-white/40 bg-white/12 text-white' : 'border-hairline text-text-2 hover:text-white')
                  }
                >
                  {district.district}
                </button>
              )
            })}
          </div>
        </div>

        <div>
          <SectionLabel>{t('mission.layers')}</SectionLabel>
          <ul className="flex flex-col gap-2.5">
            {(Object.keys(layers) as LayerId[]).map((id) => (
              <li key={id}>
                <div className="flex items-center justify-between gap-2">
                  <span className="text-text text-xs font-medium">{t(`layers.${id}.name`)}</span>
                  <Switch
                    checked={layers[id] && !(SMOKE_LAYERS.includes(id) && smokeState === 'none')}
                    onCheckedChange={() => toggleLayer(id)}
                    label={t(`layers.${id}.name`)}
                    accent={accents[id]}
                    disabled={SMOKE_LAYERS.includes(id) && smokeState === 'none'}
                  />
                </div>
                <p className="text-text-2 mt-0.5 text-[11px] leading-snug">
                  {id === 'scars' ? `${t('layers.scars.legend')} (zoom ${SCAR_MIN_ZOOM}+)` : t(`layers.${id}.legend`)}
                </p>
                {SMOKE_LAYERS.includes(id) && smokeState !== 'ready' ? (
                  id === 'smoke' && (
                    <p className="text-text-2 mt-1 text-[10px] italic">
                      {t(smokeState === 'none' ? 'legend.smokeMissing' : 'legend.smokeOutside')}
                    </p>
                  )
                ) : (
                  <LayerLegend id={id} />
                )}
              </li>
            ))}
          </ul>
          <p className="text-text-2 mt-2.5 text-[10px] leading-snug">{t('legend.scan')}</p>
        </div>

        <div className="text-text-2 flex items-center gap-1.5 text-[11px]">
          <InfoPopover label={t('mission.credits')} side="right">
            <ul className="flex flex-col gap-1.5">
              {(
                ['sentinel', 'firms', 'worldcover', 'winds', 'places', 'boundaries', 'naturalEarth', 'limits'] as const
              ).map((key) => (
                <li key={key}>{t(`credits.${key}`)}</li>
              ))}
              {!usingAmazonLocation && <li>{t('map.basemapFallback')}</li>}
            </ul>
          </InfoPopover>
          {t('mission.credits')}
        </div>
      </div>
    </Panel>
  )
})
