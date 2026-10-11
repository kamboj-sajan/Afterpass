/** Colours shared by the map layers, charts and legends. RGB triples in 0-255. */

export type RGB = [number, number, number]
export type RGBA = [number, number, number, number]

export const EMBER: RGB = [255, 107, 44]
export const EMBER_CORE: RGB = [255, 227, 163]
export const OFFICIAL: RGB = [61, 214, 245]
export const TEXT: RGB = [232, 236, 245]
/** The page background, for rims and halos that separate marks from what is under them. */
export const INK: RGB = [5, 7, 13]

const MIDPOINT: RGB = [255, 227, 163]

function mix(a: RGB, b: RGB, t: number): RGB {
  return [0, 1, 2].map((i) => Math.round(a[i] + (b[i] - a[i]) * t)) as RGB
}

/**
 * Cyan (all recorded) through pale gold to ember (all unrecorded). Passing through a light
 * midpoint keeps the ramp readable; cyan and orange mixed directly give a muddy grey.
 */
export function shareColor(share: number): RGB {
  const t = Math.min(1, Math.max(0, share))
  return t < 0.5 ? mix(OFFICIAL, MIDPOINT, t * 2) : mix(MIDPOINT, EMBER, (t - 0.5) * 2)
}

export function withAlpha(color: RGB, alpha: number): RGBA {
  return [color[0], color[1], color[2], Math.round(alpha * 255)]
}

export function css(color: RGB, alpha = 1): string {
  return `rgba(${color[0]}, ${color[1]}, ${color[2]}, ${alpha})`
}

/** CSS gradient of the share ramp, for legends. */
export function shareGradient(): string {
  const stops = [0, 0.25, 0.5, 0.75, 1].map((t) => `${css(shareColor(t))} ${t * 100}%`)
  return `linear-gradient(90deg, ${stops.join(', ')})`
}
