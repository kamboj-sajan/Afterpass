import { useTranslation } from 'react-i18next'
import { Bar, BarChart, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { EMBER, OFFICIAL, css } from '@/lib/colors'
import { formatInteger } from '@/lib/format'
import { BURN_WINDOW_HOURS } from '@/lib/time'

/**
 * FIRMS detections by IST hour. The spike around the 13:30 pass, with nothing in the shaded
 * 15:00-19:00 band where most fires now start, is the blind spot in one picture.
 */
export function HourHistogram(props: { hours: number[] }) {
  const { t } = useTranslation()
  const data = props.hours.map((count, hour) => ({ hour, count }))
  return (
    <ResponsiveContainer width="100%" height={120}>
      <BarChart data={data} margin={{ top: 14, right: 6, bottom: 0, left: 0 }} barCategoryGap={1}>
        <XAxis
          dataKey="hour"
          type="number"
          domain={[-0.5, 23.5]}
          ticks={[0, 6, 12, 18, 23]}
          tickFormatter={(hour: number) => `${String(hour).padStart(2, '0')}:00`}
          tick={{ fill: '#8A93A8', fontSize: 10 }}
          axisLine={{ stroke: 'rgba(255,255,255,0.08)' }}
          tickLine={false}
        />
        <YAxis
          width={44}
          tickFormatter={(value: number) => formatInteger(value)}
          tick={{ fill: '#8A93A8', fontSize: 10 }}
          axisLine={false}
          tickLine={false}
          allowDecimals={false}
        />
        <ReferenceArea
          x1={BURN_WINDOW_HOURS[0] - 0.5}
          x2={BURN_WINDOW_HOURS[1] - 0.5}
          fill={css(EMBER, 0.16)}
          stroke={css(EMBER, 0.5)}
          strokeDasharray="3 3"
        />
        <ReferenceLine
          x={13.5}
          stroke={css(OFFICIAL, 0.9)}
          strokeDasharray="2 3"
          label={{ value: '13:30', position: 'top', fill: css(OFFICIAL), fontSize: 10 }}
        />
        <Tooltip
          cursor={{ fill: 'rgba(255,255,255,0.06)' }}
          contentStyle={{
            background: 'rgba(14, 18, 30, 0.95)',
            border: '1px solid rgba(255,255,255,0.1)',
            borderRadius: 10,
            fontSize: 12,
          }}
          labelStyle={{ color: '#E8ECF5' }}
          labelFormatter={(hour) => {
            const start = String(hour).padStart(2, '0')
            return `${start}:00–${start}:59 IST`
          }}
          formatter={(value) => [formatInteger(Number(value)), t('chart.detections')]}
        />
        <Bar dataKey="count" fill={css(OFFICIAL, 0.85)} radius={[2, 2, 0, 0]} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  )
}
