/** `scars`: burn-scar polygons, drawn from zoom 12 up. */

import { DataFilterExtension, type DataFilterExtensionProps } from '@deck.gl/extensions'
import { GeoJsonLayer } from '@deck.gl/layers'
import type { Feature, MultiPolygon, Polygon } from 'geojson'
import { EMBER, EMBER_CORE, OFFICIAL, withAlpha } from '@/lib/colors'
import { SENTINEL_PASS_HOUR, istMs } from '@/lib/time'
import type { ScarCollection, ScarProperties } from '@/lib/types'

export type ScarFeature = Feature<Polygon | MultiPolygon, ScarProperties>

const filter = new DataFilterExtension({ filterSize: 1 })

/** One layer per loaded district file. A scar appears when the clock reaches the pass that first showed it. */
export function scarLayers(options: {
  collections: ScarCollection[]
  clockMs: number
  weekStart: number
  visible: boolean
}) {
  const { collections, clockMs, weekStart, visible } = options
  const clockMinute = (clockMs - weekStart) / 60_000
  return collections.map(
    (collection, index) =>
      new GeoJsonLayer<ScarProperties, DataFilterExtensionProps<ScarFeature>>({
        id: `scars-${collection.week}-${index}`,
        data: collection,
        visible,
        pickable: true,
        filled: true,
        stroked: true,
        // Unrecorded scars: ember fill with a bright outline. Recorded scars: cyan outline only.
        getFillColor: (f) => (f.properties.recorded ? withAlpha(OFFICIAL, 0.06) : withAlpha(EMBER, 0.4)),
        getLineColor: (f) => (f.properties.recorded ? withAlpha(OFFICIAL, 0.9) : withAlpha(EMBER_CORE, 0.95)),
        getLineWidth: 1,
        lineWidthUnits: 'pixels',
        lineWidthMinPixels: 1,
        extensions: [filter],
        getFilterValue: (f: ScarFeature) =>
          (istMs(f.properties.first_detected, SENTINEL_PASS_HOUR) - weekStart) / 60_000,
        filterRange: [-1e9, clockMinute],
      }),
  )
}
