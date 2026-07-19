// KPI 指标可视化相关类型，与后端 app/schemas/metric.py 对齐

export interface ChangeTuple {
  value: number | null
  change: number | null
  change_pct: number | null
}

export interface KpiCardData {
  metric: string
  label: string
  value: number | null
  unit: string
  yoy: ChangeTuple | null
  qoq: ChangeTuple | null
}

export interface KpiOverview {
  year: number
  period: string
  cards: KpiCardData[]
  generated_at: string
}

export interface TrendPoint {
  year: number
  value: number | null
}

export interface MetricTrend {
  metric: string
  label: string
  unit: string
  series: TrendPoint[]
}

export interface MetricComparisonItem {
  metric: string
  label: string
  unit: string
  values: Record<string, number | null>
}

export interface MetricComparison {
  year: number
  periods: string[]
  metrics: MetricComparisonItem[]
}

export interface DrillDownItem {
  period: string
  value: number | null
  ratio: number | null
}

export interface DrillDown {
  metric: string
  label: string
  year: number
  total: number | null
  items: DrillDownItem[]
}

export const PERIOD_OPTIONS = ['Q1', 'Q2', 'Q3', 'Q4', 'H1', 'H2', 'annual'] as const
