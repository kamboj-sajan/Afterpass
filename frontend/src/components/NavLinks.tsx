import { Languages } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { NavLink } from 'react-router'
import { cn } from '@/lib/cn'

const SCREENS = [
  { to: '/map', key: 'nav.map' },
  { to: '/delhi', key: 'nav.delhi' },
  { to: '/method', key: 'nav.method' },
] as const

/** The app's screens as small pills, with the language switch. Shown at the top of every panel. */
export function NavLinks(props: { className?: string }) {
  const { t, i18n } = useTranslation()
  const hindi = i18n.language.startsWith('hi')
  return (
    <nav className={cn('flex items-center gap-1', props.className)} aria-label={t('nav.label')}>
      {SCREENS.map((screen) => (
        <NavLink
          key={screen.to}
          to={screen.to}
          className={({ isActive }) =>
            cn(
              'focus-ring rounded-md px-2 py-1 text-[11px] font-medium transition-colors duration-200',
              isActive ? 'text-text bg-white/12' : 'text-text-2 hover:text-white',
            )
          }
        >
          {t(screen.key)}
        </NavLink>
      ))}
      <button
        type="button"
        aria-label={t('app.language')}
        title={t('app.language')}
        onClick={() => void i18n.changeLanguage(hindi ? 'en' : 'hi')}
        className="focus-ring text-text-2 border-hairline ml-auto inline-flex cursor-pointer items-center gap-1 rounded-md border px-1.5 py-1 text-[11px] hover:text-white"
      >
        <Languages size={12} aria-hidden />
        <span lang={hindi ? 'en' : 'hi'}>{hindi ? 'EN' : 'हिं'}</span>
      </button>
    </nav>
  )
}
