import {
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
  Tooltip as ReTooltip,
} from 'recharts'
import EmptyState from '../ui/EmptyState.tsx'
import {
  CHART_TOOLTIP_STYLE,
  CHART_LABEL_STYLE,
  CHART_AXIS_TICK,
} from './chartTokens.ts'

export interface RadarDataItem {
  metric: string
  value: number
  fullMark: number
}

interface RadarChartCardProps {
  title: string
  data: RadarDataItem[]
  height?: number
}

/**
 * 财务比率雷达图卡片
 * 用于可视化盈利能力、偿债能力、成长性、运营效率、流动性等多维财务比率。
 */
export default function RadarChartCard({
  title,
  data,
  height = 320,
}: RadarChartCardProps) {
  const hasData = data.length > 0

  return (
    <div className="card">
      <h3 className="card-title">{title}</h3>
      {hasData ? (
        <div className="chart-container" style={{ height }}>
          <ResponsiveContainer width="100%" height="100%">
            <RadarChart data={data} outerRadius="75%">
              <PolarGrid stroke="var(--color-border-light)" />
              <PolarAngleAxis dataKey="metric" tick={CHART_AXIS_TICK} />
              <PolarRadiusAxis
                angle={90}
                domain={[0, 'dataMax']}
                tick={CHART_AXIS_TICK}
              />
              <ReTooltip
                contentStyle={CHART_TOOLTIP_STYLE}
                labelStyle={CHART_LABEL_STYLE}
                formatter={(value) => [
                  typeof value === 'number'
                    ? value.toLocaleString('zh-CN')
                    : String(value),
                  '值',
                ]}
              />
              <Radar
                name={title}
                dataKey="value"
                stroke="var(--color-primary)"
                fill="var(--color-primary)"
                fillOpacity={0.4}
              />
            </RadarChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <EmptyState
          title="暂无比率数据"
          description="当前没有可用的财务比率数据。"
          icon="trend"
        />
      )}
    </div>
  )
}
