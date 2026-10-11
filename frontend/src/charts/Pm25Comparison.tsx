import { useTranslation } from 'react-i18next'
import { Area, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { css, EMBER, OFFICIAL } from '@/lib/colors'
import { formatDate } from '@/lib/format'
import type { Pm25Day } from '@/lib/types'

/** The daily Delhi-mean Smoke Arrival Index (left axis) against observed PM2.5 (right axis). */
export function Pm25Comparison(props: { series: Pm25Day[] }) {
  const { t, i18n } = useTranslation()
  const language = i18n.language
  return (
    <ResponsiveContainer width="100%" height={240}>
      <ComposedChart data={props.series} margin={{ top: 8, right: 4, bottom: 0, left: 0 }}>
        <XAxis
          dataKey="date"
          tickFormatter={(day: string) => formatDate(day, language)}
          tick={{ fill: '#8A93A8', fontSize: 10 }}
          axisLine={{ stroke: 'rgba(255,255,255,0.08)' }}
          tickLine={false}
          minTickGap={36}
        />
        <YAxis
          yAxisId="sai"
          width={34}
          tick={{ fill: css(EMBER), fontSize: 10 }}
          axisLine={false}
          tickLine={false}
          domain={[0, 'auto']}
        />
        <YAxis
          yAxisId="pm"
          orientation="right"
          width={38}
          tick={{ fill: css(OFFICIAL), fontSize: 10 }}
          axisLine={false}
          tickLine={false}
          domain={[0, 'auto']}
        />
        <Tooltip
          cursor={{ stroke: 'rgba(255,255,255,0.2)' }}
          contentStyle={{
            background: 'rgba(14, 18, 30, 0.95)',
            border: '1px solid rgba(255,255,255,0.1)',
            borderRadius: 10,
            fontSize: 12,
          }}
          labelStyle={{ color: '#E8ECF5' }}
          labelFormatter={(day) => formatDate(String(day), language, true)}
        />
        <Area
          yAxisId="sai"
          type="monotone"
          dataKey="sai"
          name={t('method.smoke.indexAxis')}
          stroke={css(EMBER)}
          fill={css(EMBER, 0.3)}
          isAnimationActive={false}
          connectNulls={false}
        />
        <Line
          yAxisId="pm"
          type="monotone"
          dataKey="pm25"
          name={t('method.smoke.pmAxis')}
          stroke={css(OFFICIAL)}
          strokeWidth={1.6}
          dot={false}
          isAnimationActive={false}
          connectNulls={false}
        />
      </ComposedChart>
    </ResponsiveContainer>
  )
}
