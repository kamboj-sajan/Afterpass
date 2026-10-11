/** Runtime configuration from Vite env vars. */

export const DATA_BASE_URL = (import.meta.env.VITE_DATA_BASE_URL ?? 'http://127.0.0.1:8787').replace(/\/$/, '')
const LOCATION_KEY = import.meta.env.VITE_LOCATION_KEY ?? ''
const AWS_REGION = import.meta.env.VITE_AWS_REGION ?? 'us-west-2'

/** The camera stays inside Punjab, Haryana and Delhi with a small margin: west, south, east, north. */
export const REGION_BOUNDS: [number, number, number, number] = [72.6, 26.9, 78.9, 33.4]

export const INITIAL_VIEW = { longitude: 75.6, latitude: 30.35, zoom: 8.1, pitch: 50, bearing: -15 }

/** Scars are only drawn (and only downloaded) from this zoom up. */
export const SCAR_MIN_ZOOM = 12

export const usingAmazonLocation = LOCATION_KEY !== ''

/**
 * Amazon Location with India's political view when a key is configured (brief §12.4);
 * otherwise the CARTO Dark Matter development fallback.
 */
export function basemapStyle(): string {
  if (usingAmazonLocation) {
    return (
      `https://maps.geo.${AWS_REGION}.amazonaws.com/v2/styles/Standard/descriptor` +
      `?key=${LOCATION_KEY}&color-scheme=Dark&political-view=IND`
    )
  }
  return 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json'
}
