import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/cn'
import { formatDateTime } from '@/lib/format'
import { useAnimatedNumber } from '@/lib/motion'
import { InfoPopover } from './ui/InfoPopover'

/** A headline number that counts up, with an ⓘ naming the file it came from. */
export function Kpi(props: {
  label: string
  note: string
  value: number | null
  format: (value: number) => string
  accent: 'official' | 'ember' | 'text'
  source: { file: string; generatedAt: string }
  /** The headline of the panel: full width, with a larger number. */
  hero?: boolean
}) {
  const { t, i18n } = useTranslation()
  const animated = useAnimatedNumber(props.value ?? 0, 700)
  const colour = { official: 'text-official', ember: 'text-ember', text: 'text-text' }[props.accent]
  return (
    <div
      className={cn(
        'min-w-0 rounded-xl border p-3',
        props.hero ? 'border-ember/30 bg-ember/8 col-span-2' : 'border-hairline bg-black/20',
      )}
    >
      <div className="flex items-start justify-between gap-1">
        <span className="text-text-2 text-[11px] leading-tight">{props.label}</span>
        <InfoPopover label={`${t('kpi.source')}: ${props.label}`}>
          <p className="text-text mb-1 font-medium">{t('kpi.source')}</p>
          <p className="font-mono break-all">{props.source.file}</p>
          <p className="mt-1">
            {t('kpi.generated', { when: formatDateTime(Date.parse(props.source.generatedAt), i18n.language) })}
          </p>
        </InfoPopover>
      </div>
      <div
        className={cn('tabular mt-1.5 leading-none font-semibold', props.hero ? 'text-4xl' : 'text-2xl', colour)}
        data-testid="kpi-value"
      >
        {props.value === null ? '–' : props.format(animated)}
      </div>
      <div className="text-text-2 mt-1.5 text-[11px] leading-tight">{props.note}</div>
    </div>
  )
}
