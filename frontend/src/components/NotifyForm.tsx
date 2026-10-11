import { BellRing } from 'lucide-react'
import { useId, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { SUBSCRIBE_URL } from '@/lib/config'
import { SectionLabel } from './ui/Panel'

/** Delhi's districts, as the alerts name them. */
const ZONES = [
  'Central',
  'East',
  'New Delhi',
  'North',
  'North East',
  'North West',
  'Shahdara',
  'South',
  'South East',
  'South West',
  'West',
]

type Status = 'idle' | 'sending' | 'sent' | 'badEmail' | 'rateLimited' | 'failed'

const FIELD =
  'border-hairline text-text placeholder:text-text-2 focus-ring w-full rounded-lg border bg-black/25 px-2.5 py-2 text-xs outline-none'

/**
 * "Notify me" (brief §12.5): an email when one part of Delhi is forecast to reach High. Shown
 * only when the alerts are deployed. SNS confirms the address before anything is sent.
 */
export function NotifyForm(props: { zone: string | null }) {
  const { t } = useTranslation()
  const emailId = useId()
  const zoneId = useId()
  const [email, setEmail] = useState('')
  const [chosen, setChosen] = useState<string | null>(null)
  const [status, setStatus] = useState<Status>('idle')
  if (SUBSCRIBE_URL === '') return null
  // Until the visitor picks one, the zone follows the locality on screen.
  const suggested = props.zone !== null && ZONES.includes(props.zone.trim()) ? props.zone.trim() : ZONES[0]
  const zone = chosen ?? suggested

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setStatus('sending')
    try {
      const response = await fetch(SUBSCRIBE_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim(), zone }),
      })
      if (response.ok) setStatus('sent')
      else if (response.status === 429) setStatus('rateLimited')
      else if (response.status === 400) setStatus('badEmail')
      else setStatus('failed')
    } catch {
      setStatus('failed')
    }
  }

  return (
    <form onSubmit={(event) => void submit(event)} className="flex flex-col gap-2" data-testid="notify-form">
      <SectionLabel>
        <span className="inline-flex items-center gap-1.5">
          <BellRing size={12} aria-hidden />
          {t('notify.heading')}
        </span>
      </SectionLabel>
      <p className="text-text-2 -mt-1 text-xs leading-snug">{t('notify.intro')}</p>
      <label htmlFor={emailId} className="sr-only">
        {t('notify.email')}
      </label>
      <input
        id={emailId}
        type="email"
        required
        autoComplete="email"
        value={email}
        onChange={(event) => setEmail(event.target.value)}
        placeholder={t('notify.email')}
        className={FIELD}
      />
      <div className="flex gap-2">
        <label htmlFor={zoneId} className="sr-only">
          {t('notify.zone')}
        </label>
        <select
          id={zoneId}
          value={zone}
          onChange={(event) => setChosen(event.target.value)}
          className={FIELD}
          aria-label={t('notify.zone')}
        >
          {ZONES.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
        <button
          type="submit"
          disabled={status === 'sending'}
          className="focus-ring bg-text text-bg shrink-0 cursor-pointer rounded-lg px-3 py-2 text-xs font-medium disabled:cursor-not-allowed disabled:opacity-50"
        >
          {status === 'sending' ? t('notify.sending') : t('notify.submit')}
        </button>
      </div>
      <p className="text-xs leading-snug" role="status">
        {status === 'sent' && <span className="text-success">{t('notify.sent')}</span>}
        {status === 'badEmail' && <span className="text-ember-2">{t('notify.badEmail')}</span>}
        {status === 'rateLimited' && <span className="text-ember-2">{t('notify.rateLimited')}</span>}
        {status === 'failed' && <span className="text-ember-2">{t('notify.failed')}</span>}
      </p>
      <p className="text-text-2 -mt-1 text-[11px] leading-snug">{t('notify.privacy')}</p>
    </form>
  )
}
