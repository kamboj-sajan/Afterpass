import type { Layer, PickingInfo } from '@deck.gl/core'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import Map, { NavigationControl, type MapRef } from 'react-map-gl/maplibre'
import { DeckOverlay } from '@/components/DeckOverlay'
import { burnsLayer, prepareBurns, type BurnCell } from '@/layers/burns'
import { delhiLayer, prepareDelhi, type DelhiCell } from '@/layers/delhi'
import { districtBounds, districtLayers, type DistrictFeature } from '@/layers/districts'
import { officialLayer, prepareOfficial, type OfficialDatum, type Sweep } from '@/layers/official'
import { scanLayer, villageLayers } from '@/layers/overlays'
import { scarLayers, type ScarFeature } from '@/layers/scars'
import { TOOLTIP_STYLE } from '@/layers/tooltip'
import { prepareSmoke, smokeLayer } from '@/layers/smoke'
import { INITIAL_VIEW, REGION_BOUNDS, SCAR_MIN_ZOOM, basemapStyle, isSmallScreen } from '@/lib/config'
import { useScars } from '@/lib/data'
import { formatDate, formatDateTime, formatHectares, formatShare, formatTime } from '@/lib/format'
import { useReducedMotion, useRise } from '@/lib/motion'
import { hourIndex, saiLevel } from '@/lib/smoke'
import { useExplorer } from '@/lib/store'
import { weekRange } from '@/lib/time'
import type { SeasonData, SmokeRun } from '@/lib/types'

/** Columns fade out over this zoom range as the scar outlines take over. */
const COLUMN_FADE: [number, number] = [SCAR_MIN_ZOOM - 0.6, SCAR_MIN_ZOOM + 0.4]

function columnOpacity(zoom: number): number {
  const [from, to] = COLUMN_FADE
  return Math.min(1, Math.max(0, (to - zoom) / (to - from))) * 0.9
}

function intersects(a: [number, number, number, number], b: [number, number, number, number]): boolean {
  return a[0] <= b[2] && a[2] >= b[0] && a[1] <= b[3] && a[3] >= b[1]
}

/** Pixels kept clear around the districts when the map opens. */
const FIT_MARGIN = 28

/** Narrowest open strip of map, in pixels, worth centring the camera on. */
const MIN_OPEN_WIDTH = 240

/** The space the panels and timeline cover, so the camera centres on the open part of the map. */
function panelPadding(): { top: number; bottom: number; left: number; right: number } {
  const style = getComputedStyle(document.documentElement)
  const px = (name: string) => Number.parseFloat(style.getPropertyValue(name)) || 0
  const edge = px('--edge')
  const left = px('--panel-left') + 2 * edge
  const right = px('--panel-right') + 2 * edge
  const sides = window.innerWidth - left - right >= MIN_OPEN_WIDTH
  return {
    top: edge,
    bottom: px('--timeline-h') + 2 * edge,
    left: sides ? left : 0,
    right: sides ? right : 0,
  }
}

export function MapView(props: { data: SeasonData; sweep: Sweep | null; smoke: SmokeRun | null }) {
  const { data, sweep, smoke } = props
  const { t, i18n } = useTranslation()
  const language = i18n.language
  const reduced = useReducedMotion()
  const mapRef = useRef<MapRef>(null)

  const season = useExplorer((s) => s.season)
  const week = useExplorer((s) => s.week)
  const districts = useExplorer((s) => s.districts)
  const layers = useExplorer((s) => s.layers)
  const clockMs = useExplorer((s) => s.clockMs)
  const camera = useExplorer((s) => s.camera)
  const highlightedDistrict = useExplorer((s) => s.highlightedDistrict)
  const highlightedVillage = useExplorer((s) => s.highlightedVillage)
  const highlightDistrict = useExplorer((s) => s.highlightDistrict)
  const flyTo = useExplorer((s) => s.flyTo)

  // Zoom is tracked to one decimal: enough for the fades, without a render per frame.
  const [zoom, setZoom] = useState(INITIAL_VIEW.zoom)
  const [view, setView] = useState<[number, number, number, number]>(REGION_BOUNDS)

  useEffect(() => {
    const map = mapRef.current
    if (!map || camera === null) return
    const target = {
      center: [camera.longitude, camera.latitude] as [number, number],
      zoom: camera.zoom,
      pitch: camera.pitch ?? map.getPitch(),
      bearing: camera.bearing ?? map.getBearing(),
    }
    if (reduced) map.jumpTo({ ...target, padding: panelPadding() })
    else map.flyTo({ ...target, padding: panelPadding(), duration: 1800, essential: true })
  }, [camera, reduced])

  const weekStart = week === null ? 0 : weekRange(week).start
  const official = useMemo(
    () => (week === null ? [] : prepareOfficial(data.firms.items, week, districts)),
    [data.firms.items, week, districts],
  )
  const cells = useMemo(
    () => (week === null ? [] : prepareBurns(data.cells.items, week, districts)),
    [data.cells.items, week, districts],
  )
  const rise = useRise(`${week}|${districts.join(',')}`, 1200)

  const trails = useMemo(() => (smoke === null ? [] : prepareSmoke(smoke.trips, isSmallScreen())), [smoke])
  const smokeHour = smoke === null ? 0 : hourIndex(smoke.summary, clockMs)
  const delhiCells = useMemo(() => (smoke === null ? [] : prepareDelhi(smoke.sai, smokeHour)), [smoke, smokeHour])

  // Scar files are large, so only the districts on screen are loaded, and only when zoomed in.
  const scarsOn = layers.scars && zoom >= SCAR_MIN_ZOOM
  const inView = useMemo(
    () =>
      data.districts.features
        .filter((f) => districts.includes(f.properties.district) && intersects(districtBounds(f), view))
        .map((f) => f.properties.district),
    [data.districts, districts, view],
  )
  const scars = useScars(season, inView, week, scarsOn)

  const dataBounds = useMemo(() => {
    const chosen = data.districts.features.filter((f) => districts.includes(f.properties.district))
    const boxes = (chosen.length > 0 ? chosen : data.districts.features).map(districtBounds)
    return [
      Math.min(...boxes.map((b) => b[0])),
      Math.min(...boxes.map((b) => b[1])),
      Math.max(...boxes.map((b) => b[2])),
      Math.max(...boxes.map((b) => b[3])),
    ] as [number, number, number, number]
  }, [data.districts, districts])

  // Opens on the selected districts, fitted into the open part of the map. Read once, on mount.
  const [initialView] = useState(() => {
    const { pitch, bearing } = INITIAL_VIEW
    if (!dataBounds.every(Number.isFinite)) return INITIAL_VIEW
    const padding = panelPadding()
    // The fit is worked out looking straight down; a tilted view needs more room at the bottom.
    padding.top += FIT_MARGIN
    padding.bottom += FIT_MARGIN * 2
    padding.left += FIT_MARGIN
    padding.right += FIT_MARGIN
    return { bounds: dataBounds, fitBoundsOptions: { padding, bearing }, pitch, bearing }
  })

  const village = useMemo(
    () => data.villages.items.find((v) => v.id === highlightedVillage) ?? null,
    [data.villages.items, highlightedVillage],
  )

  const focusDistrict = (feature: DistrictFeature) => {
    const [west, south, east, north] = districtBounds(feature)
    highlightDistrict(feature.properties.district)
    flyTo({ longitude: (west + east) / 2, latitude: (south + north) / 2, zoom: 9.2 })
  }

  const districtParts = districtLayers({
    districts: data.districts,
    selected: districts,
    highlighted: highlightedDistrict,
    visible: layers.districts,
    onClick: focusDistrict,
  })
  // Later layers draw over earlier ones.
  const deckLayers: Layer[] = [
    districtParts.outlines,
    burnsLayer({ data: cells, rise, opacity: columnOpacity(zoom), visible: layers.burns }),
    ...scarLayers({ collections: scars, clockMs, weekStart, visible: scarsOn }),
    delhiLayer({ data: delhiCells, visible: layers.delhi && smoke !== null }),
    smokeLayer({
      data: trails,
      runStart: smoke?.trips.start ?? 0,
      clockMs,
      visible: layers.smoke && smoke !== null,
    }),
    scanLayer(dataBounds, sweep?.progress ?? null),
    officialLayer({ data: official, clockMs, weekStart, sweep, visible: layers.official }),
    districtParts.labels,
    ...villageLayers(village),
  ]

  const tooltip = ({ object, layer }: PickingInfo) => {
    if (!object || !layer) return null
    let lines: string[]
    if (layer.id === 'official') {
      const { point } = object as OfficialDatum
      lines = [
        t('tooltip.firms', {
          time: formatTime(point.ist, language),
          satellite: t(`satellite.${point.sat}`, { defaultValue: point.sat }),
        }),
        formatDate(point.ist.slice(0, 10), language, true),
      ]
      if (point.frp !== null) lines.push(t('tooltip.frp', { value: point.frp }))
    } else if (layer.id === 'burns') {
      const cell = object as BurnCell
      lines = [
        t('tooltip.cell', { burned: formatHectares(cell.burnedHa) }),
        t('tooltip.cellShare', { share: formatShare(cell.share) }),
      ]
    } else if (layer.id.startsWith('scars-')) {
      const scar = (object as ScarFeature).properties
      lines = [
        t(scar.recorded ? 'tooltip.scarRecorded' : 'tooltip.scarUnrecorded'),
        t('tooltip.scarDetail', {
          area: formatHectares(scar.area_ha),
          date: formatDate(scar.first_detected, language),
        }),
      ]
    } else if (layer.id === 'delhi' && smoke !== null) {
      const cell = object as DelhiCell
      lines = [
        t('tooltip.delhi', { value: cell.sai, level: t(`smoke.level.${saiLevel(cell.sai)}`) }),
        `${formatDateTime(smoke.sai.hours[smokeHour] * 1000, language)} IST`,
      ]
    } else if (layer.id === 'districts') {
      const district = (object as DistrictFeature).properties
      lines = [
        district.district,
        t('tooltip.district', {
          burned: formatHectares(district.burned_ha),
          share: formatShare(district.unrecorded_share),
        }),
      ]
    } else {
      return null
    }
    return { text: lines.join('\n'), style: TOOLTIP_STYLE }
  }

  return (
    <Map
      ref={mapRef}
      initialViewState={initialView}
      mapStyle={basemapStyle()}
      maxBounds={REGION_BOUNDS}
      minZoom={6.5}
      maxPitch={70}
      attributionControl={{ compact: true }}
      onMove={(event) => {
        const next = Math.round(event.viewState.zoom * 10) / 10
        setZoom((current) => (current === next ? current : next))
      }}
      onMoveEnd={(event) => {
        const bounds = event.target.getBounds()
        setView([bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()])
      }}
      style={{ position: 'absolute', inset: 0 }}
    >
      <DeckOverlay interleaved layers={deckLayers} getTooltip={tooltip} />
      <NavigationControl position="bottom-right" visualizePitch showZoom showCompass />
    </Map>
  )
}
