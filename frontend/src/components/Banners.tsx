import { CloudOff } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { formatDate } from '@/lib/format'
import { coverageNotes } from '@/lib/metrics'
import { useExplorer } from '@/lib/store'
import type { SeasonData } from '@/lib/types'

/** Plain-language notes about gaps in the imagery for the week on screen. */
export function Banners(props: { data: SeasonData }) {
  const { t, i18n } = useTranslation()
  const week = useExplorer((s) => s.week)
  const districts = useExplorer((s) => s.districts)
  const notes = coverageNotes(props.data.summary, districts, week)
  if (notes.length === 0) return null
  return (
    <ul className="flex flex-col items-center gap-1.5" role="status">
      {notes.map((note) => (
        <li
          key={`${note.kind}-${note.district}`}
          className="panel text-text-2 flex max-w-[520px] items-start gap-2 px-3 py-2 text-xs leading-snug"
        >
          <CloudOff size={14} className="mt-0.5 shrink-0" aria-hidden />
          {note.kind === 'missing' &&
            t('banner.missing', {
              district: note.district,
              dates: note.dates.map((day) => formatDate(day, i18n.language)).join(', '),
            })}
          {note.kind === 'no-pass' && t('banner.noPass', { district: note.district })}
          {note.kind === 'partial' && t('banner.partial', { district: note.district, pct: Math.round(note.bestPct) })}
        </li>
      ))}
    </ul>
  )
}
