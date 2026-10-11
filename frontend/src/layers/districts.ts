/** `districts`: outlines and labels, with hover and focus highlights. */

import { GeoJsonLayer, TextLayer } from '@deck.gl/layers'
import type { Feature, MultiPolygon, Polygon, Position } from 'geojson'
import { INK, TEXT, withAlpha } from '@/lib/colors'
import type { DistrictCollection, DistrictProperties } from '@/lib/types'

export type DistrictFeature = Feature<Polygon | MultiPolygon, DistrictProperties>

function outerRings(feature: DistrictFeature): Position[][] {
  return feature.geometry.type === 'Polygon'
    ? [feature.geometry.coordinates[0]]
    : feature.geometry.coordinates.map((polygon) => polygon[0])
}

/** [west, south, east, north] of a district. */
export function districtBounds(feature: DistrictFeature): [number, number, number, number] {
  const points = outerRings(feature).flat()
  const lons = points.map((p) => p[0])
  const lats = points.map((p) => p[1])
  return [Math.min(...lons), Math.min(...lats), Math.max(...lons), Math.max(...lats)]
}

export function districtCentre(feature: DistrictFeature): [number, number] {
  const [west, south, east, north] = districtBounds(feature)
  return [(west + east) / 2, (south + north) / 2]
}

/** Returns the outlines (drawn on the ground) and the labels (drawn above everything else). */
export function districtLayers(options: {
  districts: DistrictCollection
  selected: string[]
  highlighted: string | null
  visible: boolean
  onClick: (feature: DistrictFeature) => void
}) {
  const { districts, selected, highlighted, visible, onClick } = options
  const isOn = (f: { properties: DistrictProperties }) => selected.includes(f.properties.district)
  const isLit = (f: { properties: DistrictProperties }) => f.properties.district === highlighted
  return {
    outlines: new GeoJsonLayer<DistrictProperties>({
      id: 'districts',
      data: districts,
      visible,
      pickable: true,
      stroked: true,
      filled: true,
      // A nearly invisible fill keeps the whole district hoverable and clickable.
      getFillColor: (f) => withAlpha(TEXT, isLit(f) ? 0.05 : 0.004),
      getLineColor: (f) => withAlpha(TEXT, isLit(f) ? 0.95 : isOn(f) ? 0.5 : 0.18),
      getLineWidth: (f) => (isLit(f) ? 2.5 : 1.2),
      lineWidthUnits: 'pixels',
      autoHighlight: true,
      highlightColor: [232, 236, 245, 22],
      onClick: (info) => {
        if (info.object) onClick(info.object as DistrictFeature)
      },
      updateTriggers: {
        getFillColor: [highlighted],
        getLineColor: [highlighted, selected.join('|')],
        getLineWidth: [highlighted],
      },
    }),
    labels: new TextLayer<DistrictFeature>({
      id: 'district-labels',
      data: districts.features,
      visible,
      getPosition: (f) => districtCentre(f),
      getText: (f) => f.properties.district.toUpperCase(),
      getSize: 16,
      getColor: (f) => withAlpha(TEXT, isOn(f) ? 0.95 : 0.4),
      fontFamily: '"Space Grotesk Variable", "Inter Variable", sans-serif',
      fontWeight: 600,
      fontSettings: { sdf: true },
      outlineWidth: 3,
      outlineColor: withAlpha(INK, 0.9),
      getTextAnchor: 'middle',
      getAlignmentBaseline: 'center',
      parameters: { depthCompare: 'always' },
      updateTriggers: { getColor: [selected.join('|')] },
    }),
  }
}
