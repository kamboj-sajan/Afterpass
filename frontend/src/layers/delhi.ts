/** `delhi`: the Smoke Arrival Index over Delhi's H3 resolution-7 cells for the clock's hour (brief §12.4). */

import { H3HexagonLayer } from '@deck.gl/geo-layers'
import { receptorColor, SMOKE, withAlpha } from '@/lib/colors'
import type { DelhiSai } from '@/lib/types'

export interface DelhiCell {
  h3: string
  sai: number
}

export function prepareDelhi(sai: DelhiSai, hour: number): DelhiCell[] {
  return Object.entries(sai.cells).map(([h3, values]) => ({ h3, sai: values[hour] ?? 0 }))
}

/** Metres of column per index point: 100 stands about 4 km tall. */
const METRES_PER_POINT = 40

/**
 * Columns change once per model hour. They are not animated: deck.gl attribute transitions on
 * H3 columns make luma.gl warn about the column geometry's buffer layout.
 */
export function delhiLayer(options: { data: DelhiCell[]; visible: boolean }) {
  const { data, visible } = options
  return new H3HexagonLayer<DelhiCell>({
    id: 'delhi',
    data,
    visible,
    pickable: true,
    extruded: true,
    coverage: 0.9,
    getHexagon: (d) => d.h3,
    getElevation: (d) => d.sai,
    elevationScale: METRES_PER_POINT,
    // Cells with no smoke stay as a faint footprint so Delhi is visible before the smoke arrives;
    // light smoke is translucent, so only the cells that matter stand out.
    getFillColor: (d) =>
      d.sai > 0 ? withAlpha(receptorColor(d.sai), 0.3 + 0.6 * (d.sai / 100)) : withAlpha(SMOKE, 0.12),
    material: { ambient: 0.6, diffuse: 0.55, shininess: 20, specularColor: [253, 230, 138] },
  })
}
