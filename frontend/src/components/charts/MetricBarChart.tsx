import {
  BarChart,
  Bar,
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

interface MetricBarChartProps {
  data: Array<{ period: string; value: number | null }>
  label: string
  unit: string
}

export default function MetricBarChart({ data, label, unit }: MetricBarChartProps) {
  const hasData = data.some((point) => point.value !== null && point.value !== undefined)
  if (!hasData) {
    return <EmptyState title="暂无对比数据" description="所选周期范围内没有可用数据。" icon="reports" />
  }

  return (
    <div className="chart-container chart-container-lg">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 4 }}>
          <CartesianGrid {...CHART_GRID_PROPS} />
          <XAxis
            dataKey="period"
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
            cursor={{ fill: 'var(--color-primary-subtle)' }}
            formatter={(value) => [
              typeof value === 'number' ? `${formatTick(value)} ${unit}` : '—',
              label,
            ]}
          />
          <Bar dataKey="value" fill="var(--color-primary)" radius={[6, 6, 0, 0]} maxBarSize={48} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
