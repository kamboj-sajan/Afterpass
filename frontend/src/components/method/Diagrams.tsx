import { useTranslation } from 'react-i18next'
import { css, EMBER, OFFICIAL, SMOKE } from '@/lib/colors'

const AXIS = 'rgba(255,255,255,0.18)'
const LABEL = '#8A93A8'
const TEXT = '#E8ECF5'

/**
 * Near-infrared and shortwave-infrared reflectance for crop, straw and char, as bars.
 * A schematic: the heights show which band is brighter for each surface, not measured values.
 */
export function NbrDiagram() {
  const { t } = useTranslation()
  const surfaces = [
    { key: 'crop', nir: 78, swir: 22, verdict: t('method.scar.nbrHigh'), colour: '#34D399' },
    { key: 'straw', nir: 58, swir: 52, verdict: t('method.scar.nbrZero'), colour: '#E8D9A8' },
    { key: 'char', nir: 20, swir: 40, verdict: t('method.scar.nbrLow'), colour: css(EMBER) },
  ] as const
  const summary = surfaces.map((s) => `${t(`method.scar.${s.key}`)}: ${s.verdict}`).join('. ')
  return (
    <figure className="m-0">
      <svg viewBox="0 0 420 170" className="w-full" role="img" aria-label={summary}>
        <line x1="20" y1="120" x2="400" y2="120" stroke={AXIS} />
        {surfaces.map((surface, index) => {
          const x = 48 + index * 126
          return (
            <g key={surface.key}>
              <rect x={x} y={120 - surface.nir} width="34" height={surface.nir} rx="3" fill={surface.colour} />
              <rect
                x={x + 40}
                y={120 - surface.swir}
                width="34"
                height={surface.swir}
                rx="3"
                fill={surface.colour}
                opacity="0.45"
              />
              <text x={x + 17} y="134" textAnchor="middle" fontSize="9" fill={LABEL}>
                {t('method.scar.nir')}
              </text>
              <text x={x + 57} y="134" textAnchor="middle" fontSize="9" fill={LABEL}>
                {t('method.scar.swir')}
              </text>
              <text x={x + 37} y="150" textAnchor="middle" fontSize="11" fontWeight="600" fill={TEXT}>
                {t(`method.scar.${surface.key}`)}
              </text>
              <text x={x + 37} y="164" textAnchor="middle" fontSize="10" fill={surface.colour}>
                {surface.verdict}
              </text>
            </g>
          )
        })}
      </svg>
      <figcaption className="text-text-2 mt-1 text-[11px]">{t('method.schematic')}</figcaption>
    </figure>
  )
}

/**
 * Five days on a line: a late-afternoon fire on day 1, the scar that lasts until the field is
 * tilled, and the Sentinel-2 passes that can see it. A schematic of the idea, not a real field.
 */
export function PersistDiagram() {
  const { t } = useTranslation()
  const day = (n: number) => 30 + (n - 1) * 78
  const passes = [1, 3, 6]
  const fireX = day(1) + 78 * (16.5 / 24)
  const tilledX = day(4) + 40
  const seenX = day(3) + 78 * (11 / 24)
  const summary = `${t('method.persist.fire')}; ${t('method.persist.visible')}; ${t('method.persist.seen')}`
  return (
    <figure className="m-0">
      <svg viewBox="0 0 440 150" className="w-full" role="img" aria-label={summary}>
        <line x1={day(1)} y1="92" x2={day(6)} y2="92" stroke={AXIS} />
        {[1, 2, 3, 4, 5].map((n) => (
          <g key={n}>
            <line x1={day(n)} y1="88" x2={day(n)} y2="96" stroke={AXIS} />
            <text x={day(n) + 39} y="110" textAnchor="middle" fontSize="9" fill={LABEL}>
              {t('method.persist.day', { n })}
            </text>
          </g>
        ))}
        {/* The scar: from the fire until the field is tilled. */}
        <rect x={fireX} y="70" width={tilledX - fireX} height="12" rx="3" fill={css(EMBER, 0.55)} />
        <text x={(fireX + tilledX) / 2} y="64" textAnchor="middle" fontSize="10" fill={css(EMBER)}>
          {t('method.persist.visible')}
        </text>
        <circle cx={fireX} cy="76" r="6" fill={css(EMBER)} />
        <text x={fireX} y="46" textAnchor="middle" fontSize="10" fill={TEXT}>
          {t('method.persist.fire')}
        </text>
        <line x1={fireX} y1="50" x2={fireX} y2="68" stroke={css(EMBER, 0.6)} strokeDasharray="2 2" />
        <line x1={tilledX} y1="64" x2={tilledX} y2="88" stroke={css(SMOKE)} strokeDasharray="2 2" />
        <text x={tilledX + 4} y="60" fontSize="10" fill={css(SMOKE)}>
          {t('method.persist.tilled')}
        </text>
        {passes.slice(0, 2).map((n) => {
          const x = day(n) + 78 * (11 / 24)
          return (
            <g key={n}>
              <line x1={x} y1="20" x2={x} y2="92" stroke={css(OFFICIAL, 0.75)} />
              <rect x={x - 4} y="14" width="8" height="8" rx="1.5" fill={css(OFFICIAL)} />
            </g>
          )
        })}
        <text x={day(1) + 78 * (11 / 24) + 8} y="22" fontSize="10" fill={css(OFFICIAL)}>
          {t('method.persist.pass')}
        </text>
        <text x={seenX} y="132" textAnchor="middle" fontSize="10" fontWeight="600" fill={css(OFFICIAL)}>
          {t('method.persist.seen')}
        </text>
        <line x1={seenX} y1="96" x2={seenX} y2="122" stroke={css(OFFICIAL, 0.6)} strokeDasharray="2 2" />
      </svg>
      <figcaption className="text-text-2 mt-1 text-[11px]">{t('method.schematic')}</figcaption>
    </figure>
  )
}
