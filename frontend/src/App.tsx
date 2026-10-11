import { lazy, Suspense, useCallback, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { BrowserRouter, Navigate, Outlet, Route, Routes, useMatch } from 'react-router'
import { Toaster } from 'sonner'
import { Explorer } from './app/Explorer'
import { Hero, type HeroContext } from './app/Hero'

const Delhi = lazy(() => import('./app/Delhi').then((module) => ({ default: module.Delhi })))
const Method = lazy(() => import('./app/Method').then((module) => ({ default: module.Method })))

/**
 * The hero and the Explorer share one map: the Explorer stays mounted under the hero, so
 * "Explore the map" is a cross-fade into a map that is already drawn (brief §12.3).
 */
function MapLayout() {
  const onHero = useMatch('/') !== null
  const [warm, setWarm] = useState(false)
  const warmUp = useCallback(() => setWarm(true), [])
  return (
    <>
      {(warm || !onHero) && (
        <div className="absolute inset-0" inert={onHero} aria-hidden={onHero}>
          <Explorer />
        </div>
      )}
      <Outlet context={{ warmUp } satisfies HeroContext} />
    </>
  )
}

function SkipLink() {
  const { t } = useTranslation()
  return (
    <a
      href="#main"
      className="bg-text text-bg focus-ring sr-only z-[60] rounded-md px-3 py-2 text-sm font-medium focus:not-sr-only focus:fixed focus:top-2 focus:left-2"
    >
      {t('app.skip')}
    </a>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <SkipLink />
      <Suspense fallback={null}>
        <Routes>
          <Route element={<MapLayout />}>
            <Route index element={<Hero />} />
            <Route path="map" element={null} />
          </Route>
          <Route path="delhi" element={<Delhi />} />
          <Route path="method" element={<Method />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
      <Toaster theme="dark" position="bottom-center" />
    </BrowserRouter>
  )
}
