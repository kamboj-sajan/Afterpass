import { X } from 'lucide-react'
import { memo, useEffect, useMemo, useState } from 'react'
import { ReactCompareSlider, useReactCompareSliderContext } from 'react-compare-slider'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/cn'
import { css, EMBER_CORE } from '@/lib/colors'
import { dataUrl, imageryPath, useImagery, useScars } from '@/lib/data'
import { formatDate, formatHectares } from '@/lib/format'
import { useExplorer } from '@/lib/store'
import { isoWeekOf } from '@/lib/time'
import type { ImageryMeta, ScarCollection, SeasonData } from '@/lib/types'
import { Segmented } from './ui/Segmented'
import { Switch } from './ui/Switch'

type Mode = 'tc' | 'swir'

/** SVG path data, in percent of the crop, for scars first seen on the "after" date. */
function outlinePaths(meta: ImageryMeta, collections: ScarCollection[]): string[] {
  const [west, south, east, north] = meta.bounds
  const paths: string[] = []
  for (const collection of collections) {
    for (const feature of collection.features) {
      if (feature.properties.first_detected !== meta.post_date) continue
      const polygons =
        feature.geometry.type === 'Polygon' ? [feature.geometry.coordinates] : feature.geometry.coordinates
      for (const rings of polygons) {
        const outer = rings[0]
        const inside = outer.some(([lon, lat]) => lon >= west && lon <= east && lat >= south && lat <= north)
        if (!inside) continue
        const path = rings
          .map(
            (ring) =>
              ring
                .map(([lon, lat], index) => {
                  const x = ((lon - west) / (east - west)) * 100
                  const y = ((north - lat) / (north - south)) * 100
                  return `${index === 0 ? 'M' : 'L'}${x.toFixed(2)} ${y.toFixed(2)}`
                })
                .join(' ') + ' Z',
          )
          .join(' ')
        paths.push(path)
      }
    }
  }
  return paths
}

function Frame(props: { src: string; alt: string; label: string; side: 'left' | 'right'; paths?: string[] }) {
  return (
    <div className="relative size-full">
      <img src={props.src} alt={props.alt} className="block size-full object-cover" draggable={false} />
      {props.paths && props.paths.length > 0 && (
        <svg
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          className="pointer-events-none absolute inset-0 size-full"
          aria-hidden
        >
          {props.paths.map((d, index) => (
            <path
              key={index}
              d={d}
              fill="none"
              stroke={css(EMBER_CORE, 0.95)}
              strokeWidth={1.4}
              vectorEffect="non-scaling-stroke"
            />
          ))}
        </svg>
      )}
      <span
        className={cn(
          'absolute bottom-2 rounded-md bg-black/65 px-2 py-0.5 text-[11px] text-white',
          props.side === 'left' ? 'left-2' : 'right-2',
        )}
      >
        {props.label}
      </span>
    </div>
  )
}

/** Lets the story move the divider by itself. Draws nothing. */
function AutoWipe() {
  const { setPosition } = useReactCompareSliderContext()
  const wipe = useExplorer((s) => s.imageryWipe)
  useEffect(() => {
    if (wipe !== null) setPosition(wipe)
  }, [wipe, setPosition])
  return null
}

/** Before/after Sentinel-2 crops for a village, with a draggable divider. */
export const ImageryDrawer = memo(function ImageryDrawer(props: { data: SeasonData }) {
  const { t, i18n } = useTranslation()
  const language = i18n.language
  const season = useExplorer((s) => s.season)
  const villageId = useExplorer((s) => s.imageryVillage)
  const openImagery = useExplorer((s) => s.openImagery)
  const [mode, setMode] = useState<Mode>('tc')
  const [outlines, setOutlines] = useState(true)

  const imagery = useImagery(season, villageId, villageId !== null && props.data.imagery.has(villageId))
  const meta = imagery?.status === 'ready' && imagery.data !== 'missing' ? imagery.data : null
  const village = props.data.villages.items.find((v) => v.id === villageId) ?? null
  const scars = useScars(
    season,
    meta === null ? [] : [meta.district],
    meta === null ? null : isoWeekOf(meta.post_date),
    meta !== null && outlines,
  )
  const paths = useMemo(() => (meta === null ? [] : outlinePaths(meta, scars)), [meta, scars])

  useEffect(() => {
    if (villageId === null) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') openImagery(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [villageId, openImagery])

  if (villageId === null) return null
  const title = t('imagery.title', {
    name: meta?.name ?? village?.name ?? villageId,
    district: meta?.district ?? village?.district ?? '',
  })
  const file = (key: 'pre' | 'post') => {
    if (meta === null) return ''
    return dataUrl(imageryPath(season, meta.village_id, meta.files[`${key}_${mode}`]))
  }

  return (
    <aside
      className="panel flex w-[min(460px,calc(100vw-2rem))] flex-col"
      aria-label={title}
      data-testid="imagery-drawer"
    >
      <header className="flex items-start justify-between gap-2 px-4 pt-3.5 pb-2">
        <div className="min-w-0">
          <h2 className="font-display text-text truncate text-sm font-semibold">{title}</h2>
          {meta !== null && (
            <p className="text-ember tabular text-[11px]">
              {t('imagery.window', { value: formatHectares(meta.window_unrecorded_ha) })}
            </p>
          )}
        </div>
        <button
          type="button"
          aria-label={t('imagery.close')}
          onClick={() => openImagery(null)}
          className="focus-ring text-text-2 inline-flex size-7 shrink-0 cursor-pointer items-center justify-center rounded-md hover:text-white"
        >
          <X size={16} aria-hidden />
        </button>
      </header>

      <div className="px-4 pb-4">
        {imagery?.status === 'loading' && (
          <div className="skeleton aspect-square w-full" role="status" aria-label={t('imagery.loading')} />
        )}
        {imagery?.status === 'error' && <p className="text-text-2 text-xs">{t('imagery.error')}</p>}
        {imagery?.status === 'ready' && imagery.data === 'missing' && (
          <p className="text-text-2 text-xs leading-relaxed">{t('imagery.missing')}</p>
        )}
        {meta !== null && (
          <>
            <div className="border-hairline aspect-square w-full overflow-hidden rounded-xl border">
              <ReactCompareSlider
                aria-label={t('imagery.slider')}
                defaultPosition={50}
                style={{ width: '100%', height: '100%' }}
                itemOne={
                  <>
                    <AutoWipe />
                    <Frame
                      src={file('pre')}
                      alt={t('imagery.before', { date: formatDate(meta.pre_date, language, true) })}
                      label={t('imagery.before', { date: formatDate(meta.pre_date, language) })}
                      side="left"
                    />
                  </>
                }
                itemTwo={
                  <Frame
                    src={file('post')}
                    alt={t('imagery.after', { date: formatDate(meta.post_date, language, true) })}
                    label={t('imagery.after', { date: formatDate(meta.post_date, language) })}
                    side="right"
                    paths={outlines ? paths : undefined}
                  />
                }
              />
            </div>
            <div className="mt-3 flex items-center justify-between gap-3">
              <Segmented
                label={t('imagery.trueColour')}
                value={mode}
                onChange={setMode}
                options={[
                  { value: 'tc', label: t('imagery.trueColour') },
                  { value: 'swir', label: t('imagery.swir') },
                ]}
              />
              <label className="text-text-2 inline-flex items-center gap-2 text-xs">
                {t('imagery.outline')}
                <Switch checked={outlines} onCheckedChange={setOutlines} label={t('imagery.outline')} accent="ember" />
              </label>
            </div>
            {outlines && (
              <p className="text-text-2 mt-2 text-[11px] leading-snug">
                {t('imagery.outlineNote', { date: formatDate(meta.post_date, language) })}
              </p>
            )}
            {mode === 'swir' && <p className="text-text-2 mt-2 text-[11px] leading-snug">{t('imagery.swirNote')}</p>}
            <p className="text-text-2 mt-2 text-[10px]">
              {t('imagery.attribution', { year: meta.post_date.slice(0, 4) })}
            </p>
          </>
        )}
      </div>
    </aside>
  )
})
