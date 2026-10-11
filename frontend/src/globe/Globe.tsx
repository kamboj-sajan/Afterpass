import { useEffect, useImperativeHandle, useMemo, useRef, useState, type Ref } from 'react'
import GlobeGL, { type GlobeMethods } from 'react-globe.gl'
import * as THREE from 'three'

/** What the hero asks of the globe. */
export interface GlobeHandle {
  /** Flies down to Punjab. Resolves when the camera has arrived. */
  dive: () => Promise<void>
}

export type Phase = 'approach' | 'pass' | 'after'

interface Site {
  lat: number
  lng: number
}

const EMBER = '#ff6b2c'
const CYAN = '#3dd6f5'
/** Countries in view once the camera has settled over North India. */
const NEARBY = new Set(['IND', 'PAK', 'NPL'])
const DELHI: Site = { lat: 28.61, lng: 77.21 }
/** Where the camera settles: North India, close enough to see Punjab and Delhi apart. */
const SETTLED = { lat: 29.2, lng: 76.6, altitude: 0.3 }
const PUNJAB = { lat: 30.35, lng: 75.6 }
const ORBIT_LNG = 75.6
// Lower than the settled camera, so the satellite crosses in front of it.
const ORBIT_ALTITUDE = 0.1
/** One loop of the scene: the pass, then the afternoon. */
const CYCLE_MS = 16_000
const PASS_AT_MS = 2600
const AFTER_AT_MS = 5600
const DIVE_MS = 1500
/** The scan line crosses these latitudes during the pass. */
const SCAN_LATS: [number, number] = [29.2, 32.4]
const SCAN_LNGS: [number, number] = [73.6, 77.4]

function phaseAt(ms: number): Phase {
  if (ms < PASS_AT_MS) return 'approach'
  return ms < AFTER_AT_MS ? 'pass' : 'after'
}

/** A box body with two solar panels, glowing at the edges. */
function buildSatellite(): THREE.Group {
  const group = new THREE.Group()
  const body = new THREE.Mesh(
    new THREE.BoxGeometry(1.6, 1.6, 2.4),
    new THREE.MeshStandardMaterial({ color: '#c9d2e3', emissive: CYAN, emissiveIntensity: 0.35, metalness: 0.4 }),
  )
  group.add(body)
  const panelMaterial = new THREE.MeshStandardMaterial({
    color: '#1b3a66',
    emissive: CYAN,
    emissiveIntensity: 0.5,
    side: THREE.DoubleSide,
  })
  for (const side of [-1, 1]) {
    const panel = new THREE.Mesh(new THREE.PlaneGeometry(3.6, 1.4), panelMaterial)
    panel.position.x = side * 2.8
    panel.rotation.x = Math.PI / 2
    group.add(panel)
  }
  return group
}

/**
 * The hero's night globe (brief §12.3): land as dots, a satellite on a polar orbit that scans
 * Punjab at the 13:30 pass, then ember rings and smoke arcs towards Delhi. The cyan dots are
 * real official detections; the embers and arcs are an illustration, and the hero says so.
 */
export default function Globe(props: {
  ref?: Ref<GlobeHandle>
  countries: object[]
  /** Official detections to blink at the pass (real locations). */
  detections: Site[]
  /** Where the embers bloom after the pass. */
  embers: Site[]
  onPhase: (phase: Phase) => void
  onReady: () => void
}) {
  const { ref, countries, detections, embers, onPhase, onReady } = props
  const globe = useRef<GlobeMethods | undefined>(undefined)
  const holder = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ width: 0, height: 0 })
  const [phase, setPhase] = useState<Phase>('approach')
  const [ready, setReady] = useState(false)
  const diving = useRef(false)

  useEffect(() => {
    const node = holder.current
    if (!node) return
    const observer = new ResizeObserver(([entry]) => {
      setSize({ width: Math.round(entry.contentRect.width), height: Math.round(entry.contentRect.height) })
    })
    observer.observe(node)
    return () => observer.disconnect()
  }, [])

  useImperativeHandle(ref, () => ({
    dive: () =>
      new Promise<void>((resolve) => {
        diving.current = true
        const instance = globe.current
        if (!instance) return resolve()
        instance.controls().autoRotate = false
        instance.pointOfView({ ...PUNJAB, altitude: 0.07 }, DIVE_MS)
        window.setTimeout(resolve, DIVE_MS)
      }),
  }))

  // The satellite, its ground track and the scan line are plain three.js objects moved every
  // frame, so the animation never re-renders React.
  useEffect(() => {
    const instance = globe.current
    if (!ready || !instance) return
    const scene = instance.scene()
    const at = (lat: number, lng: number, altitude: number) => {
      const p = instance.getCoords(lat, lng, altitude)
      return new THREE.Vector3(p.x, p.y, p.z)
    }

    const satellite = buildSatellite()
    satellite.scale.setScalar(0.42)
    const track = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints([
        ...Array.from({ length: 91 }, (_, i) => at(-90 + i * 2, ORBIT_LNG, 0.004)),
        ...Array.from({ length: 91 }, (_, i) => at(90 - i * 2, ORBIT_LNG + 180, 0.004)),
      ]),
      new THREE.LineBasicMaterial({ color: CYAN, transparent: true, opacity: 0.22 }),
    )
    const scanMaterial = new THREE.LineBasicMaterial({ color: CYAN, transparent: true, opacity: 0.95 })
    const scan = new THREE.Line(new THREE.BufferGeometry(), scanMaterial)
    scene.add(satellite, track, scan)

    const renderer = instance.renderer()
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio))
    const controls = instance.controls()
    controls.enableZoom = false
    controls.autoRotate = true
    controls.autoRotateSpeed = 0.6
    instance.pointOfView({ lat: 12, lng: 40, altitude: 2.3 })
    const settle = window.setTimeout(() => {
      if (diving.current) return
      controls.autoRotate = false
      instance.pointOfView(SETTLED, 3200)
    }, 900)

    let frame = 0
    let last: Phase | null = null
    const started = performance.now()
    const tick = (now: number) => {
      const ms = (now - started) % CYCLE_MS
      // The satellite climbs north along its orbit and is over Punjab at the pass.
      const lat = -8 + (ms / CYCLE_MS) * 190
      satellite.position.copy(at(lat > 90 ? 180 - lat : lat, lat > 90 ? ORBIT_LNG + 180 : ORBIT_LNG, ORBIT_ALTITUDE))
      satellite.lookAt(0, 0, 0)

      const current = phaseAt(ms)
      if (current === 'pass') {
        const progress = (ms - PASS_AT_MS) / (AFTER_AT_MS - PASS_AT_MS)
        const scanLat = SCAN_LATS[0] + (SCAN_LATS[1] - SCAN_LATS[0]) * Math.min(1, progress * 1.15)
        scan.geometry.setFromPoints(
          Array.from({ length: 12 }, (_, i) =>
            at(scanLat, SCAN_LNGS[0] + ((SCAN_LNGS[1] - SCAN_LNGS[0]) * i) / 11, 0.006),
          ),
        )
      }
      scan.visible = current === 'pass'
      if (current !== last) {
        last = current
        setPhase(current)
        onPhase(current)
      }
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)

    // Nothing is drawn while the tab is hidden.
    const onVisibility = () => {
      if (document.hidden) instance.pauseAnimation()
      else instance.resumeAnimation()
    }
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      cancelAnimationFrame(frame)
      window.clearTimeout(settle)
      document.removeEventListener('visibilitychange', onVisibility)
      scene.remove(satellite, track, scan)
    }
  }, [ready, onPhase])

  const material = useMemo(
    () => new THREE.MeshPhongMaterial({ color: '#070b17', emissive: '#03050b', shininess: 6 }),
    [],
  )
  const seen = phase === 'approach' ? [] : detections
  const after = phase === 'after'
  const rings = useMemo(
    () => (after ? [...embers.map((site) => ({ ...site, delhi: false })), { ...DELHI, delhi: true }] : []),
    [after, embers],
  )
  const arcs = useMemo(
    () =>
      after
        ? embers.slice(0, 9).map((site) => ({
            startLat: site.lat,
            startLng: site.lng,
            endLat: DELHI.lat,
            endLng: DELHI.lng,
          }))
        : [],
    [after, embers],
  )

  return (
    <div ref={holder} className="absolute inset-0" aria-hidden>
      {size.width > 0 && (
        <GlobeGL
          ref={globe}
          width={size.width}
          height={size.height}
          // The globe sits right of centre, clear of the headline.
          globeOffset={[size.width > 900 ? size.width * 0.17 : 0, 0]}
          backgroundColor="rgba(0,0,0,0)"
          globeMaterial={material}
          showAtmosphere
          atmosphereColor={CYAN}
          atmosphereAltitude={0.13}
          onGlobeReady={() => {
            setReady(true)
            onReady()
          }}
          hexPolygonsData={countries}
          // Finer dots where the camera settles; the rest of the world stays coarse and cheap.
          hexPolygonResolution={(feature) =>
            NEARBY.has((feature as { properties: { code: string } }).properties.code) ? 4 : 3
          }
          hexPolygonMargin={0.62}
          hexPolygonUseDots
          hexPolygonAltitude={0.002}
          hexPolygonColor={(feature) =>
            (feature as { properties: { code: string } }).properties.code === 'IND'
              ? 'rgba(232,236,245,0.62)'
              : 'rgba(138,147,168,0.34)'
          }
          pointsData={seen}
          pointAltitude={0.003}
          pointRadius={0.07}
          pointColor={() => CYAN}
          pointsMerge
          ringsData={rings}
          ringColor={(ring: object) => (t: number) =>
            (ring as { delhi: boolean }).delhi ? `rgba(220,38,38,${1 - t})` : `rgba(255,107,44,${1 - t})`
          }
          ringMaxRadius={(ring: object) => ((ring as { delhi: boolean }).delhi ? 1.3 : 0.75)}
          ringPropagationSpeed={0.9}
          ringRepeatPeriod={(ring: object) => ((ring as { delhi: boolean }).delhi ? 700 : 1100)}
          arcsData={arcs}
          arcColor={() => [EMBER, 'rgba(154,164,184,0.85)']}
          arcAltitude={0.035}
          arcStroke={0.22}
          arcDashLength={0.45}
          arcDashGap={0.25}
          arcDashAnimateTime={2400}
        />
      )}
    </div>
  )
}
