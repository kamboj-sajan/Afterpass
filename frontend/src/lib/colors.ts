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

/** Smoke, brief §12.2: grey, used at 30–70% alpha. Fresh smoke starts amber and greys with age. */
export const SMOKE: RGB = [154, 164, 184]
export const SMOKE_FRESH: RGB = [255, 181, 71]

/** Delhi receptor ramp for the Smoke Arrival Index, low to high. */
const RECEPTOR_STOPS: RGB[] = [
  [253, 230, 138],
  [249, 115, 22],
  [220, 38, 38],
  [127, 29, 29],
]

/** Colour of an index value (0–100) on the receptor ramp. */
export function receptorColor(sai: number): RGB {
  const t = (Math.min(100, Math.max(0, sai)) / 100) * (RECEPTOR_STOPS.length - 1)
  const i = Math.min(RECEPTOR_STOPS.length - 2, Math.floor(t))
  return mix(RECEPTOR_STOPS[i], RECEPTOR_STOPS[i + 1], t - i)
}

/** Smoke colour for an age in hours: amber when fresh, grey after about half a day. */
export function smokeColor(ageHours: number): RGB {
  return mix(SMOKE_FRESH, SMOKE, Math.min(1, Math.max(0, ageHours / 12)))
}

export function receptorGradient(): string {
  const stops = [0, 25, 50, 75, 100].map((v) => `${css(receptorColor(v))} ${v}%`)
  return `linear-gradient(90deg, ${stops.join(', ')})`
}
