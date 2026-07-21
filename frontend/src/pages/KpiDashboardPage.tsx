import { useCallback, useEffect, useMemo, useState } from 'react'
import { ICONS } from '../components/ui/Icons.tsx'
import EmptyState from '../components/ui/EmptyState.tsx'
import { getErrorMessage } from '../utils/errors.ts'
import { formatDateTime, formatMetricValue } from '../utils/format.ts'
import KpiCard from '../components/charts/KpiCard.tsx'
import KpiTrendChart from '../components/charts/KpiTrendChart.tsx'
import MetricBarChart from '../components/charts/MetricBarChart.tsx'
import {
  getDrillDown,
  getKpiOverview,
  getMetricComparison,
  getMetricTrend,
} from '../api/metrics.ts'
import {
  PERIOD_OPTIONS,
  type DrillDown,
  type KpiCardData,
  type KpiOverview,
  type MetricComparison,
  type MetricTrend,
} from '../types/metric.ts'

const CURRENT_YEAR = new Date().getFullYear()
const YEAR_OPTIONS = [CURRENT_YEAR - 3, CURRENT_YEAR - 2, CURRENT_YEAR - 1, CURRENT_YEAR]

const PERIOD_LABELS: Record<string, string> = {
  Q1: 'Q1（第一季度）',
  Q2: 'Q2（第二季度）',
  Q3: 'Q3（第三季度）',
  Q4: 'Q4（第四季度）',
  H1: '上半年',
  H2: '下半年',
  annual: '全年',
}

function getDefaultPeriod(): string {
  const month = new Date().getMonth() + 1
  if (month <= 3) return 'Q1'
  if (month <= 6) return 'Q2'
  if (month <= 9) return 'Q3'
  return 'Q4'
}
const COMPARISON_PERIODS = ['Q1', 'Q2', 'Q3', 'Q4']

const FALLBACK_METRICS: KpiCardData[] = [
  { metric: 'revenue', label: '营收', value: null, unit: '元', yoy: null, qoq: null },
]

export default function KpiDashboardPage() {
  const [year, setYear] = useState(CURRENT_YEAR)
  const [period, setPeriod] = useState<string>(getDefaultPeriod())

  const [overview, setOverview] = useState<KpiOverview | null>(null)
  const [overviewLoading, setOverviewLoading] = useState(false)
  const [overviewError, setOverviewError] = useState('')

  const [trendMetric, setTrendMetric] = useState('revenue')
  const [trend, setTrend] = useState<MetricTrend | null>(null)
  const [trendLoading, setTrendLoading] = useState(false)
  const [trendError, setTrendError] = useState('')

  const [comparisonMetric, setComparisonMetric] = useState('revenue')
  const [comparison, setComparison] = useState<MetricComparison | null>(null)
  const [comparisonLoading, setComparisonLoading] = useState(false)
  const [comparisonError, setComparisonError] = useState('')

  const [drillMetric, setDrillMetric] = useState<string | null>(null)
  const [drill, setDrill] = useState<DrillDown | null>(null)
  const [drillLoading, setDrillLoading] = useState(false)
  const [drillError, setDrillError] = useState('')

  const metricOptions = overview?.cards ?? FALLBACK_METRICS

  const fetchOverview = useCallback(async () => {
    setOverviewLoading(true)
    setOverviewError('')
    try {
      const data = await getKpiOverview(year, period)
      setOverview(data)
    } catch (err) {
      setOverviewError(getErrorMessage(err, '加载 KPI 概览失败'))
    } finally {
      setOverviewLoading(false)
    }
  }, [year, period])

  const fetchTrend = useCallback(async () => {
    setTrendLoading(true)
    setTrendError('')
    try {
      const years = [year - 2, year - 1, year]
      const data = await getMetricTrend(trendMetric, years)
      setTrend(data)
    } catch (err) {
      setTrendError(getErrorMessage(err, '加载趋势失败'))
    } finally {
      setTrendLoading(false)
    }
  }, [trendMetric, year])

  const fetchComparison = useCallback(async () => {
    setComparisonLoading(true)
    setComparisonError('')
    try {
      const data = await getMetricComparison(year, COMPARISON_PERIODS)
      setComparison(data)
    } catch (err) {
      setComparisonError(getErrorMessage(err, '加载对比失败'))
    } finally {
      setComparisonLoading(false)
    }
  }, [year])

  const fetchDrill = useCallback(async () => {
    if (!drillMetric) {
      setDrill(null)
      return
    }
    setDrillLoading(true)
    setDrillError('')
    try {
      const data = await getDrillDown(drillMetric, year)
      setDrill(data)
    } catch (err) {
      setDrillError(getErrorMessage(err, '加载钻取失败'))
    } finally {
      setDrillLoading(false)
    }
  }, [drillMetric, year])

  useEffect(() => {
    fetchOverview()
  }, [fetchOverview])

  useEffect(() => {
    fetchTrend()
  }, [fetchTrend])

  useEffect(() => {
    fetchComparison()
  }, [fetchComparison])

  useEffect(() => {
    fetchDrill()
  }, [fetchDrill])

  const handleRefresh = () => {
    fetchOverview()
    fetchTrend()
    fetchComparison()
    if (drillMetric) fetchDrill()
  }

  const comparisonItem = useMemo(
    () => comparison?.metrics?.find((m) => m.metric === comparisonMetric) ?? null,
    [comparison, comparisonMetric],
  )
  const comparisonChartData = useMemo(() => {
    if (!comparison || !comparisonItem) return []
    return (comparison.periods ?? []).map((p) => ({ period: p, value: comparisonItem.values[p] ?? null }))
  }, [comparison, comparisonItem])

  // 提取 sparkline 数据（每个指标最近 8 个季度）
  const sparkMap = useMemo(() => {
    const map: Record<string, { period: string; value: number }[]> = {}
    const metrics = comparison?.metrics
    const periods = comparison?.periods ?? []
    if (metrics && periods.length > 0) {
      metrics.forEach((m) => {
        map[m.metric] = periods
          .map((p) => ({ period: p, value: m.values[p] ?? 0 }))
          .filter((p) => p.value !== 0 || periods.length < 4)
      })
    }
    return map
  }, [comparison])

  return (
    <div className="container">
      <div className="page-header">
        <div>
          <h1>财务指标看板</h1>
          <p className="text-muted text-sm">财务指标可视化分析，支持同比环比、趋势、对比与钻取。</p>
        </div>
        <div className="kpi-header-actions">
          <button type="button" className="secondary" onClick={handleRefresh} aria-label="刷新" data-testid="kpi-refresh">
            <ICONS.refresh size={16} />
            刷新
          </button>
        </div>
      </div>

      <div className="kpi-toolbar">
        <div className="form-group">
          <label htmlFor="kpi-year">年度</label>
          <select id="kpi-year" value={year} onChange={(e) => setYear(Number(e.target.value))} data-testid="kpi-year-select">
            {YEAR_OPTIONS.map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        </div>
        <div className="form-group">
          <label htmlFor="kpi-period">周期</label>
          <select id="kpi-period" value={period} onChange={(e) => setPeriod(e.target.value)} data-testid="kpi-period-select">
            {PERIOD_OPTIONS.map((p) => (
              <option key={p} value={p}>{PERIOD_LABELS[p] || p}</option>
            ))}
          </select>
        </div>
        {overview?.generated_at && (
          <div className="kpi-toolbar-meta">
            <span className="kpi-toolbar-meta-dot" />
            <span>更新于 {formatDateTime(overview.generated_at)}</span>
          </div>
        )}
      </div>

      {overviewError && (
        <div className="alert alert-error mb-4" role="alert">{overviewError}</div>
      )}

      <section className="kpi-section">
        <div className="dashboard-card-head">
          <h3 className="card-title">核心指标（{PERIOD_LABELS[period] || period}）</h3>
          <span className="card-meta">{overview?.cards?.length ?? 0} 项</span>
        </div>
        {overviewLoading && !overview ? (
          <div className="skeleton-stat-grid">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="skeleton skeleton-stat" style={{ height: '90px' }} />
            ))}
          </div>
        ) : overview && (overview.cards?.length ?? 0) > 0 ? (
          <div className="kpi-grid">
            {overview.cards.map((card) => (
              <KpiCard
                key={card.metric}
                label={card.label}
                value={card.value}
                unit={card.unit}
                yoy={card.yoy}
                qoq={card.qoq}
                spark={sparkMap[card.metric]}
                active={drillMetric === card.metric}
                onClick={() => setDrillMetric(card.metric)}
              />
            ))}
          </div>
        ) : (
          <EmptyState
            title="暂无 KPI 数据"
            description="该年度与周期下没有可用的财务指标，请切换到其他时间或导入财务数据后重试"
            icon="trend"
            size="md"
          />
        )}
      </section>

      <div className="dashboard-grid">
        <div className="card card-wide kpi-section">
          <div className="dashboard-card-head">
            <h3 className="card-title">年度趋势</h3>
            <div className="form-group kpi-toolbar">
              <label htmlFor="kpi-trend-metric">指标</label>
              <select
                id="kpi-trend-metric"
                value={trendMetric}
                onChange={(e) => setTrendMetric(e.target.value)}
                data-testid="kpi-trend-metric-select"
              >
                {metricOptions.map((c) => (
                  <option key={c.metric} value={c.metric}>{c.label}</option>
                ))}
              </select>
            </div>
          </div>
          {trendError ? (
            <div className="alert alert-error">{trendError}</div>
          ) : trendLoading && !trend ? (
            <div className="skeleton skeleton-block" style={{ height: '300px' }} />
          ) : trend ? (
            <KpiTrendChart data={trend.series ?? []} label={trend.label ?? ''} unit={trend.unit ?? '元'} />
          ) : (
            <EmptyState title="暂无数据" icon="trend" size="sm" />
          )}
        </div>

        <div className="card card-wide kpi-section">
          <div className="dashboard-card-head">
            <h3 className="card-title">季度对比</h3>
            <div className="form-group kpi-toolbar">
              <label htmlFor="kpi-comparison-metric">指标</label>
              <select
                id="kpi-comparison-metric"
                value={comparisonMetric}
                onChange={(e) => setComparisonMetric(e.target.value)}
                data-testid="kpi-comparison-metric-select"
              >
                {metricOptions.map((c) => (
                  <option key={c.metric} value={c.metric}>{c.label}</option>
                ))}
              </select>
            </div>
          </div>
          {comparisonError ? (
            <div className="alert alert-error">{comparisonError}</div>
          ) : comparisonLoading && !comparison ? (
            <div className="skeleton skeleton-block" style={{ height: '300px' }} />
          ) : comparisonItem ? (
            <MetricBarChart
              data={comparisonChartData}
              label={comparisonItem.label}
              unit={comparisonItem.unit}
            />
          ) : (
            <EmptyState title="暂无数据" icon="reports" size="sm" />
          )}
        </div>
      </div>

      <section className="card kpi-section">
        <div className="dashboard-card-head">
          <h3 className="card-title">明细钻取</h3>
          <span className="card-meta">
            {drillMetric
              ? `当前：${metricOptions.find((m) => m.metric === drillMetric)?.label ?? drillMetric}`
              : '点击上方指标卡查看分周期占比'}
          </span>
        </div>
        {drillError ? (
          <div className="alert alert-error">{drillError}</div>
        ) : !drillMetric ? (
          <EmptyState
            title="未选择指标"
            description="点击上方任意 KPI 卡片即可查看该指标各周期占比"
            icon="queries"
            size="sm"
          />
        ) : drillLoading && !drill ? (
          <div className="skeleton skeleton-block" style={{ height: '240px' }} />
        ) : drill && (drill.items?.length ?? 0) > 0 ? (
          <table className="kpi-drill-table" data-testid="kpi-drill-table">
            <thead>
              <tr>
                <th>周期</th>
                <th>数值</th>
                <th>占比</th>
              </tr>
            </thead>
            <tbody>
              {(drill.items ?? []).map((item) => (
                <tr key={item.period}>
                  <td>{item.period}</td>
                  <td>{formatMetricValue(item.value, metricOptions.find((m) => m.metric === drillMetric)?.unit ?? '元')}</td>
                  <td>
                    {item.ratio === null ? '—' : `${(item.ratio * 100).toFixed(2)}%`}
                    {item.ratio !== null && (
                      <span
                        className="kpi-drill-ratio-bar"
                        style={{ width: `${Math.max(item.ratio * 100, 2)}%` }}
                        aria-hidden="true"
                      />
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td>合计</td>
                <td>{formatMetricValue(drill.total, metricOptions.find((m) => m.metric === drillMetric)?.unit ?? '元')}</td>
                <td>100.00%</td>
              </tr>
            </tfoot>
          </table>
        ) : (
          <EmptyState
            title="该指标本年暂无数据"
            description="请尝试切换指标或年度"
            icon="documents"
            size="sm"
          />
        )}
      </section>
    </div>
  )
}
