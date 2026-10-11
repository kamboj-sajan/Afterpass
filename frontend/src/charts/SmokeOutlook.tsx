import { useTranslation } from 'react-i18next'
import { Area, AreaChart, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { css, receptorColor } from '@/lib/colors'
import { formatDateTime, formatTime } from '@/lib/format'
import type { PeakWindow } from '@/lib/smoke'
import { saiLevel } from '@/lib/smoke'

interface Point {
  ms: number
  sai: number
}

/** A locality's 48-hour Smoke Arrival Index, with the clock's hour and the peak window marked. */
export function SmokeOutlookChart(props: {
  hours: number[]
  sai: number[]
  nowMs: number | null
  peak: PeakWindow | null
  height?: number
}) {
  const { t, i18n } = useTranslation()
  const language = i18n.language
  const data: Point[] = props.hours.map((hour, i) => ({ ms: hour * 1000, sai: props.sai[i] }))
  const top = receptorColor(80)
  const bottom = receptorColor(10)
  return (
    <ResponsiveContainer width="100%" height={props.height ?? 120}>
      <AreaChart data={data} margin={{ top: 6, right: 6, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id="sai-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={css(top)} stopOpacity={0.75} />
            <stop offset="100%" stopColor={css(bottom)} stopOpacity={0.15} />
          </linearGradient>
        </defs>
        <XAxis
          dataKey="ms"
          type="number"
          scale="time"
          domain={['dataMin', 'dataMax']}
          tickFormatter={(ms: number) => formatTime(ms, language)}
          tick={{ fill: '#8A93A8', fontSize: 10 }}
          axisLine={{ stroke: 'rgba(255,255,255,0.08)' }}
          tickLine={false}
          minTickGap={28}
        />
        <YAxis
          width={28}
          domain={[0, 100]}
          ticks={[0, 25, 50, 75, 100]}
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
          labelFormatter={(ms) => formatDateTime(Number(ms), language)}
          formatter={(value) => [
            `${Number(value)} · ${t(`smoke.level.${saiLevel(Number(value))}`)}`,
            t('smoke.indexShort'),
          ]}
        />
        {props.peak !== null && (
          <ReferenceArea x1={props.peak.start} x2={props.peak.end - 3_600_000} fill="rgba(220,38,38,0.12)" />
        )}
        <Area
          type="monotone"
          dataKey="sai"
          stroke={css(receptorColor(55))}
          fill="url(#sai-fill)"
          isAnimationActive={false}
        />
        {props.nowMs !== null && <ReferenceLine x={props.nowMs} stroke="rgba(255,255,255,0.7)" strokeDasharray="3 3" />}
      </AreaChart>
    </ResponsiveContainer>
  )
}
