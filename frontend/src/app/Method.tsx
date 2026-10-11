import { ExternalLink } from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { HourHistogram } from '@/charts/HourHistogram'
import { Pm25Comparison } from '@/charts/Pm25Comparison'
import { AskButton, ChatDrawer } from '@/components/ChatDrawer'
import { NbrDiagram, PersistDiagram } from '@/components/method/Diagrams'
import { NavLinks } from '@/components/NavLinks'
import { css, EMBER, OFFICIAL } from '@/lib/colors'
import { DATA_BASE_URL } from '@/lib/config'
import { useMethodData } from '@/lib/data'
import { formatDate, formatDateTime, formatInteger, formatShare } from '@/lib/format'

const SEASON = 2025
const IFOREST =
  'https://www.tribuneindia.com/news/delhi/satellites-miss-majority-of-stubble-fires-delhi-air-pollution-underestimated-report'
const OFFICIAL_AQI = 'https://airquality.cpcb.gov.in/AQI_India/'
const CREDITS = ['sentinel', 'firms', 'worldcover', 'winds', 'places', 'boundaries', 'naturalEarth'] as const

function Section(props: { id: string; title: string; children: ReactNode }) {
  return (
    <section aria-labelledby={props.id} className="panel flex flex-col gap-3 p-5">
      <h2 id={props.id} className="font-display text-text text-lg font-semibold">
        {props.title}
      </h2>
      {props.children}
    </section>
  )
}

function Stat(props: { value: string; label: string; accent?: 'ember' | 'official' }) {
  return (
    <div className="border-hairline rounded-xl border bg-black/20 p-3">
      <p
        className="tabular text-2xl leading-none font-semibold"
        style={{
          color: props.accent === 'ember' ? css(EMBER) : props.accent === 'official' ? css(OFFICIAL) : undefined,
        }}
      >
        {props.value}
      </p>
      <p className="text-text-2 mt-1.5 text-[11px] leading-tight">{props.label}</p>
    </div>
  )
}

function Outside(props: { href: string; children: ReactNode }) {
  return (
    <a
      href={props.href}
      target="_blank"
      rel="noreferrer"
      className="focus-ring text-official inline-flex items-center gap-1 underline-offset-2 hover:underline"
    >
      {props.children}
      <ExternalLink size={11} aria-hidden />
    </a>
  )
}

const PROSE = 'text-text text-sm leading-relaxed'
const NOTE = 'text-text-2 text-xs leading-relaxed'

/** Screen D (brief §12.6): the method in plain language, how it was checked, and its limits. */
export function Method() {
  const { t, i18n } = useTranslation()
  const language = i18n.language
  const result = useMethodData(SEASON)

  return (
    <div className="absolute inset-0 overflow-y-auto" data-testid="method-screen">
      <main id="main" className="mx-auto flex max-w-3xl flex-col gap-(--edge) p-(--edge) pb-24">
        <header className="panel flex flex-col gap-3 p-5">
          <NavLinks />
          <h1 className="font-display text-text text-2xl leading-tight font-semibold">{t('method.title')}</h1>
          <p className={PROSE}>{t('method.lede')}</p>
          {result.status === 'ready' && (
            <p className={NOTE}>
              {t('method.season', {
                season: result.data.summary.season,
                from: formatDate(result.data.summary.window[0], language, true),
                to: formatDate(result.data.summary.window[1], language, true),
              })}
            </p>
          )}
        </header>

        {result.status === 'loading' && (
          <div className="panel flex flex-col gap-3 p-5" role="status" aria-label={t('state.loading')}>
            <div className="skeleton h-5 w-48" />
            <div className="skeleton h-24" />
          </div>
        )}
        {result.status === 'error' && (
          <div className="panel p-5" role="alert">
            <h2 className="font-display text-lg font-semibold">{t('state.errorTitle')}</h2>
            <p className="text-text-2 mt-2 text-sm">{t('state.errorBody', { url: DATA_BASE_URL })}</p>
          </div>
        )}

        {result.status === 'ready' &&
          (() => {
            const { summary, validation } = result.data
            const hours = summary.firms.by_ist_hour
            const total = hours.reduce((sum, count) => sum + count, 0)
            const midday = hours.slice(12, 16).reduce((sum, count) => sum + count, 0)
            const districts = summary.districts.map((d) => d.district).join(', ')
            const source = (file: string, generatedAt: string) =>
              t('method.source', { file, when: formatDateTime(Date.parse(generatedAt), language) })
            const pm = validation.pm25
            const qa = validation.visual_qa
            return (
              <>
                <Section id="m-scar" title={t('method.scar.heading')}>
                  <p className={PROSE}>{t('method.scar.body')}</p>
                  <h3 className="text-text text-sm font-semibold">{t('method.scar.nbrTitle')}</h3>
                  <p className={PROSE}>{t('method.scar.nbrBody')}</p>
                  <NbrDiagram />
                  <p className={PROSE} data-testid="method-rule">
                    {t('method.scar.rule', {
                      nbr: validation.thresholds.t_nbr.toFixed(1),
                      mirbi: validation.thresholds.t_mirbi.toFixed(1),
                      nir: validation.thresholds.t_nir.toFixed(2),
                      dnbr: validation.thresholds.t_dnbr.toFixed(2),
                    })}
                  </p>
                </Section>

                <Section id="m-persist" title={t('method.persist.heading')}>
                  <p className={PROSE}>{t('method.persist.body')}</p>
                  <PersistDiagram />
                </Section>

                <Section id="m-miss" title={t('method.miss.heading')}>
                  <p className={PROSE} data-testid="method-midday">
                    {t('method.miss.body', {
                      season: summary.season,
                      pct: formatShare(total === 0 ? null : midday / total),
                      count: formatInteger(total),
                    })}
                  </p>
                  <div role="img" aria-label={t('method.miss.caption')}>
                    <HourHistogram hours={hours} />
                  </div>
                  <p className={NOTE}>
                    {t('method.miss.caption')} {source(`seasons/${summary.season}/summary.json`, summary.generated_at)}
                  </p>
                  <p className={PROSE}>
                    {t('method.miss.iforest')} <Outside href={IFOREST}>{t('method.miss.iforestLink')}</Outside>
                  </p>
                </Section>

                <Section id="m-match" title={t('method.match.heading')}>
                  <p className={PROSE}>{t('method.match.body')}</p>
                  <p className={PROSE}>{t('method.match.intent')}</p>
                </Section>

                <Section id="m-check" title={t('method.check.heading')}>
                  <h3 className="text-text text-sm font-semibold">
                    {t('method.check.calibration')}
                    <span className="text-text-2 font-normal">
                      {' · '}
                      {t('method.check.calibrationWhere', {
                        district: validation.district,
                        from: formatDate(validation.firms_window[0], language),
                        to: formatDate(validation.firms_window[1], language, true),
                      })}
                    </span>
                  </h3>
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                    <Stat
                      accent="official"
                      value={formatInteger(validation.samples.confident_viirs_detections)}
                      label={t('method.check.detections')}
                    />
                    <Stat
                      accent="ember"
                      value={formatShare(validation.metrics.recall_on_firms_positives)}
                      label={t('method.check.recall')}
                    />
                    <Stat
                      value={formatShare(validation.metrics.fpr_on_clear_negatives)}
                      label={t('method.check.falseFlags')}
                    />
                  </div>
                  <ul className={`${NOTE} list-disc space-y-1 pl-4`}>
                    <li>{t('method.check.caveat1')}</li>
                    <li>{t('method.check.caveat2')}</li>
                    <li>{t('method.check.caveat3')}</li>
                  </ul>
                  <h3 className="text-text mt-1 text-sm font-semibold">{t('method.check.visual')}</h3>
                  <p className={PROSE} data-testid="method-visual">
                    {qa && qa.precision.value !== null && qa.precision.wilson_95 !== null
                      ? t('method.check.visualDone', {
                          value: formatShare(qa.precision.value),
                          low: formatShare(qa.precision.wilson_95[0]),
                          high: formatShare(qa.precision.wilson_95[1]),
                          n: qa.precision.n,
                        })
                      : t('method.check.visualPending')}
                  </p>
                  <p className={NOTE}>{source(`validation/${validation.season}.json`, validation.generated_at)}</p>
                </Section>

                <Section id="m-smoke" title={t('method.smoke.heading')}>
                  <p className={PROSE}>{t('method.smoke.body')}</p>
                  <p className={PROSE}>{t('method.smoke.notChemistry')}</p>
                  <h3 className="text-text mt-1 text-sm font-semibold">{t('method.smoke.pmHeading')}</h3>
                  {pm === undefined ? (
                    <p className={PROSE}>{t('method.smoke.pmMissing')}</p>
                  ) : (
                    <>
                      <p className={PROSE}>{t('method.smoke.pmBody', { stations: pm.stations, days: pm.days })}</p>
                      <div className="grid grid-cols-2 gap-2 sm:max-w-sm">
                        <Stat
                          value={pm.pearson === null ? '–' : pm.pearson.r.toFixed(2)}
                          label={t('method.smoke.pearson')}
                        />
                        <Stat
                          value={pm.spearman === null ? '–' : pm.spearman.rho.toFixed(2)}
                          label={t('method.smoke.spearman')}
                        />
                      </div>
                      <div
                        data-testid="method-pm25"
                        role="img"
                        aria-label={`${t('method.smoke.pmHeading')}. ${t('method.smoke.pmBody', { stations: pm.stations, days: pm.days })}`}
                      >
                        <Pm25Comparison series={pm.series} />
                      </div>
                      <p className={NOTE}>
                        <span style={{ color: css(EMBER) }}>■</span> {t('method.smoke.indexAxis')}
                        {'  '}
                        <span style={{ color: css(OFFICIAL) }}>▬</span> {t('method.smoke.pmAxis')}.{' '}
                        {source(`validation/${validation.season}.json`, pm.generated_at)}
                      </p>
                      <ul className={`${NOTE} list-disc space-y-1 pl-4`}>
                        <li>{t('method.smoke.pmCaveat1')}</li>
                        <li>{t('method.smoke.pmCaveat2', { districts: pm.smoke_sources.join(', ') })}</li>
                        <li>{t('method.smoke.pmCaveat3')}</li>
                        <li>{t('method.smoke.pmCaveat4')}</li>
                      </ul>
                    </>
                  )}
                </Section>

                <Section id="m-limits" title={t('method.limits.heading')}>
                  <ul className={`${PROSE} list-disc space-y-1.5 pl-5`}>
                    {(['l1', 'l2', 'l3', 'l4', 'l5', 'l6'] as const).map((key) => (
                      <li key={key}>{t(`method.limits.${key}`)}</li>
                    ))}
                    <li>{t('method.limits.l7', { districts })}</li>
                  </ul>
                </Section>

                <Section id="m-ethics" title={t('method.ethics.heading')}>
                  <p className={PROSE}>{t('method.ethics.body')}</p>
                  <ul className={`${PROSE} list-disc space-y-1.5 pl-5`}>
                    <li>{t('method.ethics.e1')}</li>
                    <li>{t('method.ethics.e2')}</li>
                    <li>
                      {t('method.ethics.e3')} <Outside href={OFFICIAL_AQI}>{t('method.credits.aqi')}</Outside>
                    </li>
                  </ul>
                </Section>

                <Section id="m-credits" title={t('method.credits.heading')}>
                  <ul className={`${NOTE} list-disc space-y-1 pl-4`}>
                    {CREDITS.map((key) => (
                      <li key={key}>{t(`credits.${key}`)}</li>
                    ))}
                    <li>{t('method.credits.pm25')}</li>
                  </ul>
                </Section>
              </>
            )
          })()}
      </main>
      <div className="fixed right-(--edge) bottom-(--edge) z-20 flex h-12">
        <AskButton />
      </div>
      <ChatDrawer screen="method" />
    </div>
  )
}
