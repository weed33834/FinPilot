import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation } from '@tanstack/react-query'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as ReTooltip,
  ResponsiveContainer,
} from 'recharts'
import Loading from '../../components/ui/Loading.tsx'
import EmptyState from '../../components/ui/EmptyState.tsx'
import { toast } from '../../components/ui/Toaster.tsx'
import { ICONS } from '../../components/ui/Icons.tsx'
import { getErrorMessage } from '../../utils/errors.ts'
import {
  runBacktest,
  generateMockData,
  type BacktestResult,
  type StrategyType,
} from '../../api/backtesting.ts'
import {
  CHART_TOOLTIP_STYLE,
  CHART_LABEL_STYLE,
  CHART_AXIS_TICK,
  CHART_AXIS_PROPS,
  CHART_GRID_PROPS,
} from '../../components/charts/chartTokens.ts'
import { formatTick } from '../../utils/format.ts'

// 策略枚举值原样提交给 API，展示文案由 i18n 映射（strategies.<value>.label/description）
const STRATEGIES: StrategyType[] = ['sma_cross', 'momentum', 'mean_reversion']

interface MetricCard {
  key: string
  label: string
  value: string
  hint: string
}

function fmtPct(v: number): string {
  if (!Number.isFinite(v)) return '—'
  return `${(v * 100).toFixed(2)}%`
}

function fmtNum(v: number, digits = 4): string {
  if (!Number.isFinite(v)) return '—'
  return v.toFixed(digits)
}

export default function BacktestingPage() {
  const { t } = useTranslation('adminBacktesting')
  const [strategy, setStrategy] = useState<StrategyType>('sma_cross')
  const [initialCapital, setInitialCapital] = useState(1000000)
  const [periodDays, setPeriodDays] = useState(252)

  const [prices, setPrices] = useState<number[]>([])
  const [dates, setDates] = useState<string[]>([])
  const [result, setResult] = useState<BacktestResult | null>(null)

  const mockMut = useMutation({
    mutationFn: async () => {
      const res = await generateMockData(periodDays)
      return res.data
    },
    onSuccess: (data) => {
      setPrices(data.prices)
      setDates(data.dates)
      setResult(null)
      toast.success(t('toast.mockGenerated'), t('toast.mockGeneratedDesc', { count: data.prices.length }))
    },
    onError: (err) => {
      toast.error(t('toast.mockFailed'), getErrorMessage(err, t('errors.generateMockFailed')))
    },
  })

  const backtestMut = useMutation({
    mutationFn: async () => {
      if (prices.length === 0 || dates.length === 0) {
        throw new Error(t('errors.generateMockFirst'))
      }
      const res = await runBacktest(
        {
          initial_capital: initialCapital,
          strategy_type: strategy,
          period_days: periodDays,
        },
        prices,
        dates,
      )
      return res.data
    },
    onSuccess: (data) => {
      setResult(data)
      toast.success(t('toast.backtestSuccess'))
    },
    onError: (err) => {
      toast.error(t('toast.backtestFailed'), getErrorMessage(err, t('errors.runBacktestFailed')))
    },
  })

  const equityData = useMemo(
    () => (result?.equity_curve ?? []).map((p) => ({ date: p.date, value: p.value })),
    [result],
  )

  const metrics: MetricCard[] = useMemo(() => {
    if (!result) return []
    const items: Array<{ key: string; value: string }> = [
      { key: 'total_return', value: fmtPct(result.total_return) },
      { key: 'annual_return', value: fmtPct(result.annual_return) },
      { key: 'sharpe', value: fmtNum(result.sharpe_ratio, 3) },
      { key: 'max_drawdown', value: fmtPct(result.max_drawdown) },
      { key: 'alpha', value: fmtNum(result.alpha, 4) },
      { key: 'beta', value: fmtNum(result.beta, 4) },
      { key: 'win_rate', value: fmtPct(result.win_rate) },
    ]
    return items.map((m) => ({
      key: m.key,
      label: t(`metrics.${m.key}.label`),
      value: m.value,
      hint: t(`metrics.${m.key}.hint`),
    }))
  }, [result, t])

  const handleGenerateMock = () => mockMut.mutate()
  const handleRunBacktest = () => backtestMut.mutate()

  return (
    <div className="admin-model-management">
      {/* Header */}
      <div className="admin-page-header">
        <h1 className="admin-page-title">{t('title')}</h1>
        <p className="admin-page-desc">{t('subtitle')}</p>
      </div>

      {/* Config */}
      <div className="admin-card">
        <div className="admin-card-header">
          <span className="admin-card-title">{t('config.title')}</span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 16 }}>
          <div className="admin-form-row">
            <label className="admin-form-label">{t('config.strategyType')}</label>
            <select
              className="admin-form-select"
              value={strategy}
              onChange={(e) => setStrategy(e.target.value as StrategyType)}
            >
              {STRATEGIES.map((value) => (
                <option key={value} value={value}>
                  {t(`strategies.${value}.label`)}
                </option>
              ))}
            </select>
            <span className="admin-form-hint" style={{ marginTop: 4, display: 'block' }}>
              {t(`strategies.${strategy}.description`)}
            </span>
          </div>

          <div className="admin-form-row">
            <label className="admin-form-label">{t('config.initialCapital')}</label>
            <input
              className="admin-form-input"
              type="number"
              min={0}
              value={initialCapital}
              onChange={(e) => setInitialCapital(Number(e.target.value) || 0)}
            />
          </div>

          <div className="admin-form-row">
            <label className="admin-form-label">{t('config.periodDays')}</label>
            <input
              className="admin-form-input"
              type="number"
              min={1}
              value={periodDays}
              onChange={(e) => setPeriodDays(Math.max(1, Number(e.target.value) || 1))}
            />
          </div>
        </div>

        {(mockMut.isError || backtestMut.isError) && (
          <div
            className="admin-form-error"
            style={{ marginTop: 12, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}
          >
            <span>{getErrorMessage(mockMut.error || backtestMut.error, t('errors.operationFailed'))}</span>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => (backtestMut.isError ? handleRunBacktest() : handleGenerateMock())}
            >
              <ICONS.refresh size={14} />
              {t('actions.retry')}
            </button>
          </div>
        )}

        <div style={{ display: 'flex', gap: 8, marginTop: 16, flexWrap: 'wrap' }}>
          <button
            className="btn btn-secondary"
            onClick={handleGenerateMock}
            disabled={mockMut.isPending || backtestMut.isPending}
          >
            <ICONS.refresh size={14} />
            {mockMut.isPending ? t('actions.generating') : t('actions.generateMock')}
          </button>
          <button
            className="btn btn-primary"
            onClick={handleRunBacktest}
            disabled={backtestMut.isPending || mockMut.isPending || prices.length === 0}
            title={prices.length === 0 ? t('hints.generateMockFirst') : undefined}
          >
            <ICONS.trend size={14} />
            {backtestMut.isPending ? t('actions.backtesting') : t('actions.runBacktest')}
          </button>
        </div>

        {prices.length > 0 && (
          <div style={{ marginTop: 12, color: 'var(--color-text-secondary)', fontSize: 'var(--text-sm)' }}>
            {t('hints.mockLoaded', { count: prices.length })}
            <span style={{ fontFamily: 'var(--font-mono)' }}>
              {' '}
              {Math.min(...prices).toFixed(2)} – {Math.max(...prices).toFixed(2)}
            </span>
          </div>
        )}
      </div>

      {/* Loading */}
      {(mockMut.isPending || backtestMut.isPending) && (
        <Loading text={backtestMut.isPending ? t('loading.backtesting') : t('loading.generatingMock')} />
      )}

      {/* Results */}
      {result && (
        <>
          {/* Metric Cards */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12, marginBottom: 16 }}>
            {metrics.map((m) => (
              <div
                key={m.key}
                className="admin-card"
                style={{ marginBottom: 0, padding: 'var(--space-4)' }}
              >
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', marginBottom: 4 }}>
                  {m.label}
                </div>
                <div
                  style={{
                    fontFamily: 'var(--font-display)',
                    fontSize: 'var(--text-lg)',
                    fontWeight: 700,
                    color: 'var(--color-text)',
                  }}
                >
                  {m.value}
                </div>
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', marginTop: 2 }}>
                  {m.hint}
                </div>
              </div>
            ))}
          </div>

          {/* Equity Curve */}
          <div className="admin-card">
            <div className="admin-card-header">
              <span className="admin-card-title">{t('equityCurve.title')}</span>
            </div>
            {equityData.length === 0 ? (
              <EmptyState title={t('equityCurve.empty')} icon="trend" />
            ) : (
              <div className="chart-container chart-container-lg">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={equityData} margin={{ top: 8, right: 16, bottom: 8, left: 4 }}>
                    <CartesianGrid {...CHART_GRID_PROPS} />
                    <XAxis dataKey="date" tick={CHART_AXIS_TICK} {...CHART_AXIS_PROPS} />
                    <YAxis tickFormatter={formatTick} tick={CHART_AXIS_TICK} {...CHART_AXIS_PROPS} width={72} />
                    <ReTooltip
                      contentStyle={CHART_TOOLTIP_STYLE}
                      labelStyle={CHART_LABEL_STYLE}
                      formatter={(value) => [formatTick(Number(value)), t('equityCurve.tooltipLabel')]}
                    />
                    <Line
                      type="monotone"
                      dataKey="value"
                      stroke="var(--color-primary)"
                      strokeWidth={2}
                      dot={false}
                      activeDot={{ r: 4 }}
                      connectNulls
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>

          {/* Trade Log */}
          <div className="admin-card">
            <div className="admin-card-header">
              <span className="admin-card-title">{t('tradeLog.title', { count: result.trade_log.length })}</span>
            </div>
            {result.trade_log.length === 0 ? (
              <EmptyState title={t('tradeLog.empty')} icon="queries" />
            ) : (
              <div className="test-result-box" style={{ maxHeight: 320 }}>
                {JSON.stringify(result.trade_log, null, 2)}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
