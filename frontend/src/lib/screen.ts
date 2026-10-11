import { useSyncExternalStore } from 'react'

const PHONE = '(max-width: 767px)'

function subscribe(onChange: () => void): () => void {
  const media = window.matchMedia(PHONE)
  media.addEventListener('change', onChange)
  return () => media.removeEventListener('change', onChange)
}

/** True on phone-sized screens, where panels move into a bottom sheet (brief §12.2). */
export function usePhone(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => window.matchMedia(PHONE).matches,
    () => false,
  )
}
