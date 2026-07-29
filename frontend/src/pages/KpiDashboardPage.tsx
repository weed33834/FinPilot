import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ICONS } from '../components/ui/Icons.tsx'
import EmptyState from '../components/ui/EmptyState.tsx'
import { getErrorMessage } from '../utils/errors.ts'
import { formatDateTime, formatMetricValue } from '../utils/format.ts'
import KpiCard from '../components/charts/KpiCard.tsx'
import KpiTrendChart from '../components/charts/KpiTrendChart.tsx'
import MetricBarChart from '../components/charts/MetricBarChart.tsx'
import i18n from '../i18n/config.ts'
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

function getDefaultPeriod(): string {
  const month = new Date().getMonth() + 1
  if (month <= 3) return 'Q1'
  if (month <= 6) return 'Q2'
  if (month <= 9) return 'Q3'
  return 'Q4'
}
const COMPARISON_PERIODS = ['Q1', 'Q2', 'Q3', 'Q4']

interface ErrorAlertProps {
  message: string
  onRetry: () => void
  className?: string
}

/** 错误提示条 + 重试按钮，4 个数据请求各自的 error 块复用。 */
function ErrorAlert({ message, onRetry, className = '' }: ErrorAlertProps) {
  const { t } = useTranslation('kpi')
  return (
    <div className={`alert alert-error ${className}`.trim()} role="alert">
      <span>{message}</span>
      <button type="button" className="chat-error-retry" onClick={onRetry}>
        {t('actions.retry')}
      </button>
    </div>
  )
}

export default function KpiDashboardPage() {
  const { t } = useTranslation('kpi')

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

  // FALLBACK_METRICS：label/unit 走 i18n，仅在 overview 未就绪时兜底。
  const fallbackMetrics = useMemo<KpiCardData[]>(
    () => [
      {
        metric: 'revenue',
        label: t('fallbackMetrics.revenue'),
        value: null,
        unit: t('units.yuan'),
        yoy: null,
        qoq: null,
      },
    ],
    [t],
  )

  const metricOptions = overview?.cards ?? fallbackMetrics

  // PERIOD_LABELS：值通过 t() 解析，缺失时回退到原始 period 标识。
  const periodLabel = useCallback((p: string) => t(`periodLabels.${p}`, p), [t])

  const fetchOverview = useCallback(async () => {
    setOverviewLoading(true)
    setOverviewError('')
    try {
      const data = await getKpiOverview(year, period)
      setOverview(data)
    } catch (err) {
      setOverviewError(getErrorMessage(err, i18n.t('kpi:errors.loadOverviewFailed')))
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
      setTrendError(getErrorMessage(err, i18n.t('kpi:errors.loadTrendFailed')))
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
      setComparisonError(getErrorMessage(err, i18n.t('kpi:errors.loadComparisonFailed')))
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
      setDrillError(getErrorMessage(err, i18n.t('kpi:errors.loadDrillFailed')))
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

  const drillUnit = useMemo(
    () => metricOptions.find((m) => m.metric === drillMetric)?.unit ?? t('units.yuan'),
    [metricOptions, drillMetric, t],
  )

  return (
    <div className="container">
      <div className="page-header">
        <div>
          <h1>{t('title')}</h1>
          <p className="text-muted text-sm">{t('subtitle')}</p>
        </div>
        <div className="kpi-header-actions">
          <button type="button" className="secondary" onClick={handleRefresh} aria-label={t('actions.refresh.ariaLabel')} data-testid="kpi-refresh">
            <ICONS.refresh size={16} />
            {t('actions.refresh.label')}
          </button>
        </div>
      </div>

      <div className="kpi-toolbar">
        <div className="form-group">
          <label htmlFor="kpi-year">{t('filters.year.label')}</label>
          <select id="kpi-year" value={year} onChange={(e) => setYear(Number(e.target.value))} data-testid="kpi-year-select">
            {YEAR_OPTIONS.map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        </div>
        <div className="form-group">
          <label htmlFor="kpi-period">{t('filters.period.label')}</label>
          <select id="kpi-period" value={period} onChange={(e) => setPeriod(e.target.value)} data-testid="kpi-period-select">
            {PERIOD_OPTIONS.map((p) => (
              <option key={p} value={p}>{periodLabel(p)}</option>
            ))}
          </select>
        </div>
        {overview?.generated_at && (
          <div className="kpi-toolbar-meta">
            <span className="kpi-toolbar-meta-dot" />
            <span>{t('meta.updatedAt', { time: formatDateTime(overview.generated_at) })}</span>
          </div>
        )}
      </div>

      {overviewError && (
        <ErrorAlert message={overviewError} onRetry={fetchOverview} className="mb-4" />
      )}

      <section className="kpi-section">
        <div className="dashboard-card-head">
          <h3 className="card-title">{t('sections.overview', { period: periodLabel(period) })}</h3>
          <span className="card-meta">{t('meta.itemCount', { count: overview?.cards?.length ?? 0 })}</span>
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
            title={t('empty.overview.title')}
            description={t('empty.overview.description')}
            icon="trend"
            size="md"
          />
        )}
      </section>

      <div className="dashboard-grid">
        <div className="card card-wide kpi-section">
          <div className="dashboard-card-head">
            <h3 className="card-title">{t('sections.trend')}</h3>
            <div className="form-group kpi-toolbar">
              <label htmlFor="kpi-trend-metric">{t('filters.metric.label')}</label>
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
            <ErrorAlert message={trendError} onRetry={fetchTrend} />
          ) : trendLoading && !trend ? (
            <div className="skeleton skeleton-block" style={{ height: '300px' }} />
          ) : trend ? (
            <KpiTrendChart data={trend.series ?? []} label={trend.label ?? ''} unit={trend.unit ?? t('units.yuan')} />
          ) : (
            <EmptyState title={t('empty.trend.title')} icon="trend" size="sm" />
          )}
        </div>

        <div className="card card-wide kpi-section">
          <div className="dashboard-card-head">
            <h3 className="card-title">{t('sections.comparison')}</h3>
            <div className="form-group kpi-toolbar">
              <label htmlFor="kpi-comparison-metric">{t('filters.metric.label')}</label>
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
            <ErrorAlert message={comparisonError} onRetry={fetchComparison} />
          ) : comparisonLoading && !comparison ? (
            <div className="skeleton skeleton-block" style={{ height: '300px' }} />
          ) : comparisonItem ? (
            <MetricBarChart
              data={comparisonChartData}
              label={comparisonItem.label}
              unit={comparisonItem.unit}
            />
          ) : (
            <EmptyState title={t('empty.comparison.title')} icon="reports" size="sm" />
          )}
        </div>
      </div>

      <section className="card kpi-section">
        <div className="dashboard-card-head">
          <h3 className="card-title">{t('sections.drill')}</h3>
          <span className="card-meta">
            {drillMetric
              ? t('meta.drillCurrent', { metric: metricOptions.find((m) => m.metric === drillMetric)?.label ?? drillMetric })
              : t('meta.drillHint')}
          </span>
        </div>
        {drillError ? (
          <ErrorAlert message={drillError} onRetry={fetchDrill} />
        ) : !drillMetric ? (
          <EmptyState
            title={t('empty.drill.noSelection.title')}
            description={t('empty.drill.noSelection.description')}
            icon="queries"
            size="sm"
          />
        ) : drillLoading && !drill ? (
          <div className="skeleton skeleton-block" style={{ height: '240px' }} />
        ) : drill && (drill.items?.length ?? 0) > 0 ? (
          <table className="kpi-drill-table" data-testid="kpi-drill-table">
            <thead>
              <tr>
                <th>{t('drillTable.period')}</th>
                <th>{t('drillTable.value')}</th>
                <th>{t('drillTable.ratio')}</th>
              </tr>
            </thead>
            <tbody>
              {(drill.items ?? []).map((item) => (
                <tr key={item.period}>
                  <td>{item.period}</td>
                  <td>{formatMetricValue(item.value, drillUnit)}</td>
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
                <td>{t('drillTable.total')}</td>
                <td>{formatMetricValue(drill.total, drillUnit)}</td>
                <td>100.00%</td>
              </tr>
            </tfoot>
          </table>
        ) : (
          <EmptyState
            title={t('empty.drill.noData.title')}
            description={t('empty.drill.noData.description')}
            icon="documents"
            size="sm"
          />
        )}
      </section>
    </div>
  )
}
