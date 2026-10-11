/** Transient overlays: the satellite scan band and the marker for a highlighted place. */

import { PolygonLayer, ScatterplotLayer, TextLayer } from '@deck.gl/layers'
import { EMBER_CORE, INK, OFFICIAL, TEXT, withAlpha, type RGBA } from '@/lib/colors'

interface Band {
  polygon: [number, number][]
  color: RGBA
}

/**
 * A glowing band sweeping south to north across `bounds` ([west, south, east, north]).
 * It is a visual metaphor for the satellite pass, not a depiction of the instrument.
 */
export function scanLayer(bounds: [number, number, number, number], progress: number | null) {
  const [west, south, east, north] = bounds
  const pad = (east - west) * 0.15
  const lat = south + (north - south) * (progress ?? 0)
  const height = (north - south) * 0.012
  // Three stacked strips, widest and faintest first, fake a soft glow.
  const strips: [number, number][] = [
    [6, 0.07],
    [2.5, 0.16],
    [0.6, 0.85],
  ]
  const bands: Band[] = strips.map(([scale, alpha]) => ({
    polygon: [
      [west - pad, lat - height * scale],
      [east + pad, lat - height * scale],
      [east + pad, lat + height * scale],
      [west - pad, lat + height * scale],
    ],
    color: withAlpha(OFFICIAL, alpha),
  }))
  return new PolygonLayer<Band>({
    id: 'scan-line',
    data: bands,
    visible: progress !== null,
    getPolygon: (d) => d.polygon,
    getFillColor: (d) => d.color,
    stroked: false,
    parameters: { depthCompare: 'always' },
  })
}

/** A place to ring and label on the map: a highlighted village or a Delhi locality. */
export interface Marker {
  lon: number
  lat: number
  name: string
}

export function villageLayers(village: Marker | null) {
  const data = village === null ? [] : [village]
  return [
    new ScatterplotLayer<Marker>({
      id: 'village-marker',
      data,
      getPosition: (d) => [d.lon, d.lat],
      getRadius: 14,
      radiusUnits: 'pixels',
      filled: false,
      stroked: true,
      getLineColor: withAlpha(EMBER_CORE, 0.95),
      lineWidthMinPixels: 2,
      parameters: { depthCompare: 'always' },
    }),
    new TextLayer<Marker>({
      id: 'village-label',
      data,
      getPosition: (d) => [d.lon, d.lat],
      getText: (d) => d.name,
      getSize: 13,
      getColor: withAlpha(TEXT, 1),
      getPixelOffset: [0, -26],
      fontFamily: '"Inter Variable", sans-serif',
      fontWeight: 600,
      fontSettings: { sdf: true },
      outlineWidth: 3,
      outlineColor: withAlpha(INK, 0.9),
      characterSet: 'auto',
      parameters: { depthCompare: 'always' },
    }),
  ]
}
