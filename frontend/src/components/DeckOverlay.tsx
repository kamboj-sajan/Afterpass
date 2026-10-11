import { MapboxOverlay, type MapboxOverlayProps } from '@deck.gl/mapbox'
import { useControl } from 'react-map-gl/maplibre'

/** deck.gl layers drawn inside the MapLibre map. Must be a child of `<Map>`. */
export function DeckOverlay(props: MapboxOverlayProps) {
  const overlay = useControl<MapboxOverlay>(() => new MapboxOverlay(props))
  overlay.setProps(props)
  return null
}
