import type { Layer, PickingInfo } from '@deck.gl/core'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useEffect, useMemo, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import Map, { NavigationControl, type MapRef } from 'react-map-gl/maplibre'
import { DeckOverlay } from '@/components/DeckOverlay'
import { delhiLayer, prepareDelhi, type DelhiCell } from '@/layers/delhi'
import { villageLayers } from '@/layers/overlays'
import { prepareSmoke, smokeLayer } from '@/layers/smoke'
import { TOOLTIP_STYLE } from '@/layers/tooltip'
import { DELHI_VIEW, REGION_BOUNDS, basemapStyle, isSmallScreen } from '@/lib/config'
import { useDelhi } from '@/lib/delhiStore'
import { formatDateTime } from '@/lib/format'
import { useReducedMotion } from '@/lib/motion'
import { hourIndex, placeName, saiLevel } from '@/lib/smoke'
import type { SmokeLocality, SmokeRun } from '@/lib/types'

/** The space the panel and the timeline cover, so the camera centres on the open part of the map. */
function panelPadding(): { top: number; bottom: number; left: number; right: number } {
  const root = document.querySelector('[data-screen="delhi"]') ?? document.documentElement
  const style = getComputedStyle(root)
  const px = (name: string) => Number.parseFloat(style.getPropertyValue(name)) || 0
  const edge = px('--edge')
  const left = px('--panel-left') + 2 * edge
  return {
    top: edge,
    bottom: px('--timeline-h') + 2 * edge,
    left: window.innerWidth - left >= 240 ? left : 0,
    right: 0,
  }
}

/** Tilted Delhi with a column per cell for the hour's index, the smoke trails and the chosen locality. */
export function DelhiMap(props: { run: SmokeRun; locality: SmokeLocality | null }) {
  const { run, locality } = props
  const { t, i18n } = useTranslation()
  const language = i18n.language
  const reduced = useReducedMotion()
  const mapRef = useRef<MapRef>(null)
  const clockMs = useDelhi((s) => s.clockMs)
  const camera = useDelhi((s) => s.camera)
  const setLocality = useDelhi((s) => s.setLocality)

  useEffect(() => {
    const map = mapRef.current
    if (!map || camera === null) return
    const target = {
      center: [camera.longitude, camera.latitude] as [number, number],
      zoom: camera.zoom,
      pitch: camera.pitch ?? map.getPitch(),
      bearing: camera.bearing ?? map.getBearing(),
      padding: panelPadding(),
    }
    if (reduced) map.jumpTo(target)
    else map.flyTo({ ...target, duration: 1400, essential: true })
  }, [camera, reduced])

  const trails = useMemo(() => prepareSmoke(run.trips, isSmallScreen()), [run])
  const hour = hourIndex(run.summary, clockMs)
  const cells = useMemo(() => prepareDelhi(run.sai, hour), [run, hour])
  const marker = useMemo(
    () => (locality === null ? null : { lon: locality.lon, lat: locality.lat, name: placeName(locality, language) }),
    [locality, language],
  )

  // Later layers draw over earlier ones.
  const layers: Layer[] = [
    delhiLayer({ data: cells, visible: true }),
    smokeLayer({ data: trails, runStart: run.trips.start, clockMs, visible: true }),
    ...villageLayers(marker),
  ]

  const tooltip = ({ object, layer }: PickingInfo) => {
    if (!object || layer?.id !== 'delhi') return null
    const cell = object as DelhiCell
    const lines = [
      t('tooltip.delhi', { value: cell.sai, level: t(`smoke.level.${saiLevel(cell.sai)}`) }),
      `${formatDateTime(run.sai.hours[hour] * 1000, language)} IST`,
    ]
    return { text: lines.join('\n'), style: TOOLTIP_STYLE }
  }

  // Clicking a column shows the outlook of a named place inside it.
  const pick = ({ object, layer }: PickingInfo) => {
    if (!object || layer?.id !== 'delhi') return
    const inside = run.localities.find((item) => item.h3 === (object as DelhiCell).h3)
    if (inside) setLocality(inside.id)
  }

  return (
    <Map
      ref={mapRef}
      initialViewState={{ ...DELHI_VIEW, padding: panelPadding() }}
      mapStyle={basemapStyle()}
      maxBounds={REGION_BOUNDS}
      minZoom={6.5}
      maxPitch={70}
      attributionControl={{ compact: true }}
      style={{ position: 'absolute', inset: 0 }}
    >
      <DeckOverlay interleaved layers={layers} getTooltip={tooltip} onClick={pick} />
      <NavigationControl position="bottom-right" visualizePitch showZoom showCompass />
    </Map>
  )
}
