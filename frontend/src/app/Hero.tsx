import { ExternalLink, Map as MapIcon, Play } from 'lucide-react'
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useOutletContext } from 'react-router'
import { NavLinks } from '@/components/NavLinks'
import type { GlobeHandle, Phase } from '@/globe/Globe'
import { HeroStill } from '@/globe/HeroStill'
import { cn } from '@/lib/cn'
import { useSeasonData } from '@/lib/data'
import { useReducedMotion } from '@/lib/motion'

const Globe = lazy(() => import('@/globe/Globe'))

const IFOREST =
  'https://www.tribuneindia.com/news/delhi/satellites-miss-majority-of-stubble-fires-delhi-air-pollution-underestimated-report'
const SEASON = 2025
/** The fade into the map starts a moment into the dive and ends with it. */
const FADE = 'transition-opacity duration-[1200ms] delay-300 ease-in'
const MAX_DETECTIONS = 180
const MAX_EMBERS = 16
/** Centres of the mapped districts, used for the embers until the villages have loaded. */
const DISTRICT_CENTRES = [
  { lat: 30.21, lng: 75.88 },
  { lat: 30.2, lng: 75.0 },
  { lat: 30.93, lng: 74.61 },
]

/** What the layout around the hero offers it. */
export interface HeroContext {
  /** Starts loading the map underneath, so the dive ends on a drawn map. */
  warmUp: () => void
}

function hasWebGL(): boolean {
  try {
    return document.createElement('canvas').getContext('webgl2') !== null
  } catch {
    return false
  }
}

function useCountries(): object[] | null {
  const [countries, setCountries] = useState<object[] | null>(null)
  useEffect(() => {
    let cancelled = false
    fetch(`${import.meta.env.BASE_URL}globe/countries_ind.json`)
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error(String(response.status)))))
      .then((file: { features: object[] }) => {
        if (!cancelled) setCountries(file.features)
      })
      // Without the outlines the still drawing stays up.
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [])
  return countries
}

/** Screen A (brief §12.3): the globe, the headline, and the way into the map and the story. */
export function Hero() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { warmUp } = useOutletContext<HeroContext>()
  const reduced = useReducedMotion()
  const [webgl] = useState(hasWebGL)
  const [phase, setPhase] = useState<Phase>('approach')
  const [leaving, setLeaving] = useState(false)
  const globe = useRef<GlobeHandle>(null)
  const countries = useCountries()
  const season = useSeasonData(SEASON)
  const animated = webgl && !reduced && countries !== null

  const detections = useMemo(() => {
    if (season.status !== 'ready') return []
    const points = season.data.firms.items
    const step = Math.max(1, Math.floor(points.length / MAX_DETECTIONS))
    return points.filter((_, index) => index % step === 0).map((point) => ({ lat: point.lat, lng: point.lon }))
  }, [season])
  const embers = useMemo(() => {
    if (season.status !== 'ready') return DISTRICT_CENTRES
    return season.data.villages.items.slice(0, MAX_EMBERS).map((village) => ({ lat: village.lat, lng: village.lon }))
  }, [season])

  // The map loads behind the hero once the globe is drawing, or straight away without one.
  const onReady = useCallback(() => window.setTimeout(warmUp, 1200), [warmUp])
  useEffect(() => {
    if (!animated) warmUp()
  }, [animated, warmUp])

  const leave = async (to: string) => {
    if (leaving) return
    warmUp()
    if (animated && globe.current) {
      setLeaving(true)
      await globe.current.dive()
    }
    void navigate(to)
  }

  return (
    <div
      className={cn('bg-bg absolute inset-0 z-40 overflow-hidden', FADE, leaving && 'pointer-events-none opacity-0')}
      data-testid="hero"
    >
      <div className="absolute inset-0 opacity-45 lg:opacity-100">
        {animated ? (
          <Suspense fallback={<HeroStill />}>
            <Globe
              ref={globe}
              countries={countries}
              detections={detections}
              embers={embers}
              onPhase={setPhase}
              onReady={onReady}
            />
          </Suspense>
        ) : (
          <HeroStill />
        )}
      </div>

      {/* Keeps the headline readable where the globe passes behind it. */}
      <div className="from-bg via-bg/85 pointer-events-none absolute inset-y-0 left-0 w-full bg-gradient-to-r to-transparent lg:w-[58%]" />

      <main
        id="main"
        className="relative z-10 flex h-full max-w-2xl flex-col justify-between gap-6 p-6 sm:p-10 lg:p-14"
      >
        <header className="flex items-center gap-3">
          <span className="font-display text-text text-sm font-semibold tracking-[0.22em] uppercase">
            {t('app.name')}
          </span>
          <NavLinks className="flex-1" />
        </header>

        <div className="flex flex-col gap-5">
          <h1 className="font-display text-text text-4xl leading-[1.08] font-semibold text-balance sm:text-5xl lg:text-6xl">
            {t('hero.headline')}
          </h1>
          <p className="text-text max-w-xl text-base leading-relaxed sm:text-lg">{t('hero.sub')}</p>
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => void leave('/map')}
              className="focus-ring bg-ember text-bg inline-flex cursor-pointer items-center gap-2 rounded-full px-5 py-3 text-sm font-semibold transition-transform duration-200 hover:scale-[1.03]"
            >
              <MapIcon size={16} aria-hidden />
              {t('hero.explore')}
            </button>
            <button
              type="button"
              onClick={() => void leave('/map?demo=1&story=1')}
              className="focus-ring border-hairline text-text inline-flex cursor-pointer items-center gap-2 rounded-full border bg-white/5 px-5 py-3 text-sm font-semibold hover:bg-white/10"
            >
              <Play size={15} aria-hidden />
              {t('hero.story')}
            </button>
          </div>
        </div>

        <footer className="flex flex-col gap-3">
          {animated && (
            <ul className="flex flex-col gap-1.5 text-xs" aria-live="off">
              <li className={cn('transition-opacity duration-300', phase === 'after' ? 'opacity-45' : 'opacity-100')}>
                <span className="text-official font-semibold">{t('hero.passLabel')}</span>
                <span className="text-text-2"> · {t('hero.passNote')}</span>
              </li>
              <li className={cn('transition-opacity duration-300', phase === 'after' ? 'opacity-100' : 'opacity-45')}>
                <span className="text-ember font-semibold">{t('hero.afterLabel')}</span>
                <span className="border-ember/50 text-ember-2 mx-1.5 rounded-full border px-1.5 py-px text-[10px] font-medium tracking-wide uppercase">
                  {t('hero.illustration')}
                </span>
                <span className="text-text-2">{t('hero.afterNote')}</span>
              </li>
            </ul>
          )}
          <p className="text-text-2 max-w-xl text-xs leading-relaxed">
            {t('hero.footnote')}{' '}
            <a
              href={IFOREST}
              target="_blank"
              rel="noreferrer"
              className="focus-ring text-official inline-flex items-center gap-1 underline-offset-2 hover:underline"
            >
              {t('hero.footnoteLink')}
              <ExternalLink size={11} aria-hidden />
            </a>
          </p>
        </footer>
      </main>
    </div>
  )
}
