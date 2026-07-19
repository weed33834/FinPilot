import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip as ReTooltip,
  Cell,
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

export interface WaterfallItem {
  name: string
  value: number
  type: 'start' | 'increase' | 'decrease' | 'end'
}

interface WaterfallChartProps {
  title: string
  data: WaterfallItem[]
  height?: number
}

/**
 * 各类型柱子的颜色（通过 CSS 变量保持与主题一致）
 * - start: 蓝色（起点总额）
 * - increase: 绿色（正向变动）
 * - decrease: 红色（负向变动）
 * - end: 紫色（终点合计）
 */
const TYPE_COLORS: Record<WaterfallItem['type'], string> = {
  start: 'var(--color-primary)',
  increase: 'var(--color-success)',
  decrease: 'var(--color-danger)',
  end: 'var(--color-purple)',
}

interface WaterfallDatum {
  name: string
  /** 不可见的堆叠基座，用于把可见柱子顶起，形成悬浮瀑布效果 */
  base: number
  /** 可见柱子的高度 */
  value: number
  color: string
  /** 原始带符号的数值（用于 Tooltip 展示） */
  rawValue: number
  type: WaterfallItem['type']
}

/**
 * 将瀑布数据转换为堆叠柱状图所需的结构：
 * 维护一个累计值，根据类型计算每个柱子的「基座」与「高度」。
 */
function buildWaterfallData(data: WaterfallItem[]): WaterfallDatum[] {
  let cumulative = 0
  return data.map((item) => {
    const color = TYPE_COLORS[item.type]
    const raw = item.value
    let base = 0
    const barValue = Math.abs(raw)

    if (item.type === 'start' || item.type === 'end') {
      base = 0
      cumulative = raw
    } else if (item.type === 'increase') {
      base = cumulative
      cumulative += raw
    } else {
      // decrease: value 为负，柱子悬浮在累计值下方
      base = cumulative - barValue
      cumulative += raw
    }

    return { name: item.name, base, value: barValue, color, rawValue: raw, type: item.type }
  })
}

/** 带符号的数值格式化，increase 显示「+」前缀 */
function formatWaterfallValue(type: WaterfallItem['type'], value: number): string {
  const formatted = value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
  if (type === 'increase') return `+${formatted}`
  return formatted
}

interface WaterfallTooltipProps {
  active?: boolean
  payload?: Array<{ payload: WaterfallDatum }>
}

function WaterfallTooltip({ active, payload }: WaterfallTooltipProps) {
  if (!active || !payload || payload.length === 0) return null
  const datum = payload[0].payload
  return (
    <div style={{ ...CHART_TOOLTIP_STYLE, display: 'block' }}>
      <div style={CHART_LABEL_STYLE}>{datum.name}</div>
      <div style={{ color: datum.color, fontWeight: 600 }}>
        {formatWaterfallValue(datum.type, datum.rawValue)}
      </div>
    </div>
  )
}

/**
 * 损益瀑布图卡片
 * 用于展示 P&L 分解：营业收入 → 成本 → 营业利润 → 税费 → 净利润。
 * 通过不可见堆叠基座 + 可见柱子实现悬浮瀑布效果。
 */
export default function WaterfallChart({
  title,
  data,
  height = 320,
}: WaterfallChartProps) {
  const hasData = data.length > 0
  const chartData = buildWaterfallData(data)

  return (
    <div className="card">
      <h3 className="card-title">{title}</h3>
      {hasData ? (
        <div className="chart-container" style={{ height }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 8, right: 16, bottom: 8, left: 4 }}>
              <CartesianGrid {...CHART_GRID_PROPS} />
              <XAxis
                dataKey="name"
                tick={CHART_AXIS_TICK}
                interval={0}
                {...CHART_AXIS_PROPS}
              />
              <YAxis
                tickFormatter={formatTick}
                tick={CHART_AXIS_TICK}
                {...CHART_AXIS_PROPS}
                width={64}
              />
              <ReTooltip
                cursor={{ fill: 'var(--color-primary-subtle)' }}
                content={<WaterfallTooltip />}
              />
              <Bar dataKey="base" stackId="waterfall" fill="transparent" />
              <Bar
                dataKey="value"
                stackId="waterfall"
                radius={[4, 4, 0, 0]}
                maxBarSize={56}
              >
                {chartData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.color} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <EmptyState
          title="暂无盈亏数据"
          description="当前没有可用的损益分解数据。"
          icon="reports"
        />
      )}
    </div>
  )
}
