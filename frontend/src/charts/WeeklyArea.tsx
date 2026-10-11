import { useTranslation } from 'react-i18next'
import { Area, AreaChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { EMBER, OFFICIAL, css } from '@/lib/colors'
import { formatHectares, formatInteger } from '@/lib/format'
import type { WeekPoint } from '@/lib/metrics'

function weekNumber(week: string): string {
  return String(Number(week.slice(-2)))
}

/** Recorded (cyan) against unrecorded (ember) burned area, week by week. */
export function WeeklyArea(props: { data: WeekPoint[]; selectedWeek: string | null }) {
  const { t } = useTranslation()
  return (
    <ResponsiveContainer width="100%" height={132}>
      <AreaChart data={props.data} margin={{ top: 6, right: 6, bottom: 0, left: 0 }}>
        <XAxis
          dataKey="week"
          tickFormatter={(week: string) => t('chart.weekShort', { number: weekNumber(week) })}
          tick={{ fill: '#8A93A8', fontSize: 10 }}
          axisLine={{ stroke: 'rgba(255,255,255,0.08)' }}
          tickLine={false}
        />
        <YAxis
          width={52}
          tickFormatter={(value: number) => formatInteger(value)}
          tick={{ fill: '#8A93A8', fontSize: 10 }}
          axisLine={false}
          tickLine={false}
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
          labelFormatter={(week) => t('chart.weekShort', { number: weekNumber(String(week)) })}
          formatter={(value, name) => [`${formatHectares(Number(value))} ha`, name]}
        />
        <Area
          type="monotone"
          dataKey="recorded_ha"
          name={t('chart.recorded')}
          stackId="burned"
          stroke={css(OFFICIAL)}
          fill={css(OFFICIAL, 0.35)}
          isAnimationActive={false}
        />
        <Area
          type="monotone"
          dataKey="unrecorded_ha"
          name={t('chart.unrecorded')}
          stackId="burned"
          stroke={css(EMBER)}
          fill={css(EMBER, 0.45)}
          isAnimationActive={false}
        />
        {props.selectedWeek !== null && (
          <ReferenceLine x={props.selectedWeek} stroke="rgba(255,255,255,0.55)" strokeDasharray="3 3" />
        )}
      </AreaChart>
    </ResponsiveContainer>
  )
}
