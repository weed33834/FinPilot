import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as ReTooltip,
  ResponsiveContainer,
} from 'recharts'
import EmptyState from '../ui/EmptyState.tsx'
import {
  CHART_TOOLTIP_STYLE,
  CHART_LABEL_STYLE,
  CHART_AXIS_TICK,
  CHART_AXIS_PROPS,
  CHART_GRID_PROPS,
} from './chartTokens.ts'
import { formatTick } from '../../utils/format.ts'

interface KpiTrendChartProps {
  data: Array<{ year: number; value: number | null }>
  label: string
  unit: string
}

export default function KpiTrendChart({ data, label, unit }: KpiTrendChartProps) {
  const hasData = data.some((point) => point.value !== null && point.value !== undefined)
  if (!hasData) {
    return <EmptyState title="暂无趋势数据" description="所选年份范围内没有可用数据。" icon="trend" />
  }

  return (
    <div className="chart-container chart-container-lg">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 4 }}>
          <CartesianGrid {...CHART_GRID_PROPS} />
          <XAxis
            dataKey="year"
            tick={CHART_AXIS_TICK}
            {...CHART_AXIS_PROPS}
          />
          <YAxis
            tickFormatter={formatTick}
            tick={CHART_AXIS_TICK}
            {...CHART_AXIS_PROPS}
            width={64}
          />
          <ReTooltip
            contentStyle={CHART_TOOLTIP_STYLE}
            labelStyle={CHART_LABEL_STYLE}
            formatter={(value) => [
              typeof value === 'number' ? `${formatTick(value)} ${unit}` : '—',
              label,
            ]}
          />
          <Line
            type="monotone"
            dataKey="value"
            stroke="var(--color-primary)"
            strokeWidth={2}
            dot={{ r: 3, fill: 'var(--color-primary)' }}
            activeDot={{ r: 5 }}
            connectNulls
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
