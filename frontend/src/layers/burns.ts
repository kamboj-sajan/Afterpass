/** `burns`: extruded H3 columns, height by burned hectares, colour by unrecorded share. */

import { H3HexagonLayer } from '@deck.gl/geo-layers'
import { shareColor, withAlpha } from '@/lib/colors'
import type { H3Row } from '@/lib/types'

export interface BurnCell {
  h3: string
  burnedHa: number
  unrecordedHa: number
  share: number
}

/** One row per cell for the week, adding together districts that share a border cell. */
export function prepareBurns(rows: H3Row[], week: string, districts: string[]): BurnCell[] {
  const cells = new Map<string, BurnCell>()
  for (const row of rows) {
    if (row.week !== week || !districts.includes(row.district)) continue
    const cell = cells.get(row.h3) ?? { h3: row.h3, burnedHa: 0, unrecordedHa: 0, share: 0 }
    cell.burnedHa += row.burned_ha
    cell.unrecordedHa += row.unrecorded_ha
    cells.set(row.h3, cell)
  }
  for (const cell of cells.values()) {
    cell.share = cell.burnedHa > 0 ? cell.unrecordedHa / cell.burnedHa : 0
  }
  return [...cells.values()]
}

/** Metres of column height per burned hectare. A fully burned cell (about 74 ha) is ~3.3 km tall. */
const METRES_PER_HECTARE = 45

export function burnsLayer(options: { data: BurnCell[]; rise: number; opacity: number; visible: boolean }) {
  const { data, rise, opacity, visible } = options
  return new H3HexagonLayer<BurnCell>({
    id: 'burns',
    data,
    visible: visible && opacity > 0,
    opacity,
    pickable: true,
    extruded: true,
    coverage: 0.92,
    getHexagon: (d) => d.h3,
    getElevation: (d) => d.burnedHa,
    elevationScale: METRES_PER_HECTARE * rise,
    getFillColor: (d) => withAlpha(shareColor(d.share), 0.92),
    material: { ambient: 0.62, diffuse: 0.55, shininess: 24, specularColor: [255, 227, 163] },
  })
}
