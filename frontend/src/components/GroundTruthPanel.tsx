import { Images } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { HourHistogram } from '@/charts/HourHistogram'
import { WeeklyArea } from '@/charts/WeeklyArea'
import { formatDateRange, formatHectares, formatInteger, formatShare } from '@/lib/format'
import { hourHistogram, kpis, topVillages, weeklySeries } from '@/lib/metrics'
import { useExplorer } from '@/lib/store'
import { weekDates } from '@/lib/time'
import type { SeasonData } from '@/lib/types'
import { Kpi } from './Kpi'
import { Panel, SectionLabel } from './ui/Panel'
import { Segmented } from './ui/Segmented'

const VILLAGE_COUNT = 8
/** Zoom at which a village's scars are visible. */
const VILLAGE_ZOOM = 13.2

export function GroundTruthPanel(props: { data: SeasonData }) {
  const { data } = props
  const { t, i18n } = useTranslation()
  const language = i18n.language
  const season = useExplorer((s) => s.season)
  const week = useExplorer((s) => s.week)
  const districts = useExplorer((s) => s.districts)
  const scope = useExplorer((s) => s.scope)
  const setScope = useExplorer((s) => s.setScope)
  const highlightedVillage = useExplorer((s) => s.highlightedVillage)
  const highlightVillage = useExplorer((s) => s.highlightVillage)
  const openImagery = useExplorer((s) => s.openImagery)
  const flyTo = useExplorer((s) => s.flyTo)

  const numbers = kpis(data.summary, districts, scope, week)
  const villages = topVillages(data.villages.items, districts, scope, week, VILLAGE_COUNT)
  const largest = villages.length > 0 ? villages[0].unrecordedHa : 1
  const source = {
    file: `seasons/${season}/summary.json`,
    generatedAt: data.summary.generated_at,
  }
  const names = districts.length === data.summary.districts.length ? t('truth.allDistricts') : districts.join(', ')
  const dates = week === null ? null : weekDates(week)
  const scopeLine =
    scope === 'week' && dates !== null
      ? t('truth.scopeWeek', {
          range: formatDateRange(dates[0], dates[6], language),
          districts: names,
        })
      : t('truth.scopeSeason', { year: season, districts: names })

  return (
    <Panel
      title={t('truth.title')}
      className="w-(--panel-right)"
      actions={
        <Segmented
          label={t('truth.title')}
          value={scope}
          onChange={setScope}
          options={[
            { value: 'week', label: t('truth.week') },
            { value: 'season', label: t('truth.season') },
          ]}
        />
      }
    >
      <div className="scroll-thin flex min-h-0 flex-col gap-4 overflow-y-auto px-4 pb-4">
        <p className="text-text-2 -mt-1 text-[11px]" data-testid="scope-line">
          {districts.length === 0 ? t('truth.noDistricts') : scopeLine}
        </p>

        <div className="grid grid-cols-2 gap-2">
          <Kpi
            label={t('kpi.official')}
            note={t('kpi.officialNote')}
            value={numbers.officialDetections}
            format={(value) => formatInteger(Math.round(value))}
            accent="official"
            source={source}
          />
          <Kpi
            label={t('kpi.burned')}
            note={t('kpi.burnedNote')}
            value={numbers.burnedHa}
            format={(value) => formatHectares(value)}
            accent="text"
            source={source}
          />
          <Kpi
            label={t('kpi.missing')}
            note={t('kpi.missingNote')}
            value={numbers.unrecordedShare}
            format={(value) => formatShare(value)}
            accent="ember"
            source={source}
            hero
          />
        </div>

        <div>
          <SectionLabel>{t('chart.weekly')}</SectionLabel>
          <WeeklyArea data={weeklySeries(data.summary, districts)} selectedWeek={week} />
          <div className="text-text-2 mt-1 flex gap-3 text-[10px]">
            <span className="inline-flex items-center gap-1.5">
              <span className="bg-official size-2 rounded-full" />
              {t('chart.recorded')}
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="bg-ember size-2 rounded-full" />
              {t('chart.unrecorded')}
            </span>
          </div>
        </div>

        <div>
          <SectionLabel>{t('chart.hours')}</SectionLabel>
          <HourHistogram hours={hourHistogram(data.summary, districts)} />
          <p className="text-text-2 mt-1 text-[10px] leading-snug">{t('chart.hoursNote')}</p>
        </div>

        <div>
          <SectionLabel>{t('villages.title')}</SectionLabel>
          <p className="text-text-2 -mt-1 mb-2 text-[11px] leading-snug">{t('villages.subtitle')}</p>
          {villages.length === 0 ? (
            <p className="text-text-2 text-xs">{t('villages.empty')}</p>
          ) : (
            <ol className="flex flex-col gap-1">
              {villages.map(({ village, unrecordedHa }, index) => {
                const hasImagery = data.imagery.has(village.id)
                return (
                  <li key={`${village.district}-${village.id}`}>
                    <button
                      type="button"
                      aria-label={t(hasImagery ? 'villages.open' : 'villages.fly', { name: village.name })}
                      onClick={() => {
                        highlightVillage(village.id)
                        flyTo({
                          longitude: village.lon,
                          latitude: village.lat,
                          zoom: VILLAGE_ZOOM,
                        })
                        openImagery(hasImagery ? village.id : null)
                      }}
                      className={
                        'focus-ring group grid w-full cursor-pointer grid-cols-[18px_1fr_auto] items-center gap-x-2 rounded-lg px-2 py-1.5 text-left transition-colors duration-200 hover:bg-white/8 ' +
                        (village.id === highlightedVillage ? 'bg-white/10' : '')
                      }
                    >
                      <span className="tabular text-text-2 text-[11px]">{index + 1}</span>
                      <span className="min-w-0">
                        <span className="text-text flex items-center gap-1.5 text-xs font-medium">
                          <span className="truncate">{village.name}</span>
                          {hasImagery && (
                            <Images size={12} className="text-text-2 shrink-0" aria-hidden>
                              <title>{t('villages.hasImagery')}</title>
                            </Images>
                          )}
                        </span>
                        <span className="mt-1 block h-1 rounded-full bg-white/8">
                          <span
                            className="bg-ember block h-full rounded-full"
                            style={{
                              width: `${Math.max(4, (unrecordedHa / largest) * 100)}%`,
                            }}
                          />
                        </span>
                      </span>
                      <span className="tabular text-ember text-xs">
                        {t('villages.value', {
                          value: formatHectares(unrecordedHa),
                        })}
                      </span>
                    </button>
                  </li>
                )
              })}
            </ol>
          )}
        </div>
      </div>
    </Panel>
  )
}
