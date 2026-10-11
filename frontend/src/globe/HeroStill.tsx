import { useTranslation } from 'react-i18next'

/**
 * The hero scene as a still drawing, shown when WebGL is unavailable, when the visitor asked for
 * less motion, and while the globe loads.
 */
export function HeroStill() {
  const { t } = useTranslation()
  return (
    <svg
      viewBox="0 0 600 600"
      className="absolute inset-0 size-full"
      role="img"
      aria-label={t('hero.stillAlt')}
      preserveAspectRatio="xMidYMid meet"
    >
      <defs>
        <radialGradient id="still-globe" cx="38%" cy="34%" r="75%">
          <stop offset="0%" stopColor="#111a31" />
          <stop offset="100%" stopColor="#05070d" />
        </radialGradient>
        <radialGradient id="still-glow" cx="50%" cy="50%" r="50%">
          <stop offset="82%" stopColor="rgba(61,214,245,0)" />
          <stop offset="96%" stopColor="rgba(61,214,245,0.22)" />
          <stop offset="100%" stopColor="rgba(61,214,245,0)" />
        </radialGradient>
      </defs>
      <circle cx="300" cy="300" r="250" fill="url(#still-glow)" />
      <circle cx="300" cy="300" r="212" fill="url(#still-globe)" stroke="rgba(61,214,245,0.35)" />
      {/* The polar orbit and the satellite on it. */}
      <ellipse cx="300" cy="300" rx="70" ry="262" fill="none" stroke="rgba(61,214,245,0.3)" strokeDasharray="3 5" />
      <g transform="translate(262 92) rotate(-18)">
        <rect x="-5" y="-7" width="10" height="14" fill="#c9d2e3" />
        <rect x="-22" y="-4" width="15" height="8" fill="#3dd6f5" opacity="0.8" />
        <rect x="7" y="-4" width="15" height="8" fill="#3dd6f5" opacity="0.8" />
      </g>
      {/* The pass: a scan line and the detections it makes. */}
      <line x1="232" y1="238" x2="322" y2="226" stroke="#3dd6f5" strokeWidth="2" />
      {[
        [248, 252],
        [262, 244],
        [276, 256],
        [290, 246],
        [304, 250],
      ].map(([cx, cy]) => (
        <circle key={`${cx}-${cy}`} cx={cx} cy={cy} r="3" fill="#3dd6f5" />
      ))}
      <text x="236" y="216" fontSize="13" fill="#3dd6f5">
        {t('hero.passLabel')}
      </text>
      {/* After the pass: embers and the smoke's path to Delhi. */}
      {[
        [254, 276],
        [270, 286],
        [288, 274],
        [300, 290],
        [316, 278],
      ].map(([cx, cy]) => (
        <g key={`${cx}-${cy}`}>
          <circle cx={cx} cy={cy} r="9" fill="none" stroke="rgba(255,107,44,0.45)" />
          <circle cx={cx} cy={cy} r="3.5" fill="#ff6b2c" />
        </g>
      ))}
      <path d="M 290 286 Q 340 286 372 332" fill="none" stroke="#9aa4b8" strokeWidth="2" strokeDasharray="5 5" />
      <circle cx="372" cy="332" r="12" fill="none" stroke="rgba(220,38,38,0.5)" />
      <circle cx="372" cy="332" r="5" fill="#dc2626" />
      <text x="388" y="337" fontSize="13" fill="#e8ecf5">
        {t('hero.delhi')}
      </text>
      <text x="196" y="318" fontSize="13" fill="#ff6b2c">
        {t('hero.afterLabel')} · {t('hero.illustration')}
      </text>
    </svg>
  )
}
