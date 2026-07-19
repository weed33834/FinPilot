import { useMemo, useState } from 'react'
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

interface StrategyOption {
  value: StrategyType
  label: string
  description: string
}

const STRATEGIES: StrategyOption[] = [
  { value: 'sma_cross', label: '均线交叉 (SMA Cross)', description: '短期均线上穿/下穿长期均线产生买卖信号' },
  { value: 'momentum', label: '动量策略 (Momentum)', description: '基于价格动量的趋势跟随策略' },
  { value: 'mean_reversion', label: '均值回复 (Mean Reversion)', description: '价格偏离均值后向均值回归的逆向策略' },
]

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
    },
  })

  const backtestMut = useMutation({
    mutationFn: async () => {
      if (prices.length === 0 || dates.length === 0) {
        throw new Error('请先生成模拟数据')
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
    },
  })

  const equityData = useMemo(
    () => (result?.equity_curve ?? []).map((p) => ({ date: p.date, value: p.value })),
    [result],
  )

  const metrics: MetricCard[] = useMemo(() => {
    if (!result) return []
    return [
      { key: 'total_return', label: '总收益', value: fmtPct(result.total_return), hint: 'Total Return' },
      { key: 'annual_return', label: '年化收益', value: fmtPct(result.annual_return), hint: 'Annual Return' },
      { key: 'sharpe', label: '夏普比率', value: fmtNum(result.sharpe_ratio, 3), hint: 'Sharpe Ratio' },
      { key: 'max_drawdown', label: '最大回撤', value: fmtPct(result.max_drawdown), hint: 'Max Drawdown' },
      { key: 'alpha', label: 'Alpha', value: fmtNum(result.alpha, 4), hint: 'Alpha' },
      { key: 'beta', label: 'Beta', value: fmtNum(result.beta, 4), hint: 'Beta' },
      { key: 'win_rate', label: '胜率', value: fmtPct(result.win_rate), hint: 'Win Rate' },
    ]
  }, [result])

  const handleGenerateMock = () => mockMut.mutate()
  const handleRunBacktest = () => backtestMut.mutate()

  const selectedStrategy = STRATEGIES.find((s) => s.value === strategy)

  return (
    <div className="admin-model-management">
      {/* Header */}
      <div className="admin-page-header">
        <h1 className="admin-page-title">策略回测</h1>
        <p className="admin-page-desc">
          选择交易策略并配置参数，基于模拟或真实行情数据运行回测，评估收益与风险表现。
        </p>
      </div>

      {/* Config */}
      <div className="admin-card">
        <div className="admin-card-header">
          <span className="admin-card-title">回测配置</span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 16 }}>
          <div className="admin-form-row">
            <label className="admin-form-label">策略类型</label>
            <select
              className="admin-form-select"
              value={strategy}
              onChange={(e) => setStrategy(e.target.value as StrategyType)}
            >
              {STRATEGIES.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
            {selectedStrategy && (
              <span className="admin-form-hint" style={{ marginTop: 4, display: 'block' }}>
                {selectedStrategy.description}
              </span>
            )}
          </div>

          <div className="admin-form-row">
            <label className="admin-form-label">初始资金</label>
            <input
              className="admin-form-input"
              type="number"
              min={0}
              value={initialCapital}
              onChange={(e) => setInitialCapital(Number(e.target.value) || 0)}
            />
          </div>

          <div className="admin-form-row">
            <label className="admin-form-label">回测天数</label>
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
          <div className="admin-form-error" style={{ marginTop: 12 }}>
            {getErrorMessage(mockMut.error || backtestMut.error, '操作失败')}
          </div>
        )}

        <div style={{ display: 'flex', gap: 8, marginTop: 16, flexWrap: 'wrap' }}>
          <button
            className="btn btn-secondary"
            onClick={handleGenerateMock}
            disabled={mockMut.isPending || backtestMut.isPending}
          >
            <ICONS.refresh size={14} />
            {mockMut.isPending ? '生成中…' : '生成模拟数据'}
          </button>
          <button
            className="btn btn-primary"
            onClick={handleRunBacktest}
            disabled={backtestMut.isPending || mockMut.isPending || prices.length === 0}
            title={prices.length === 0 ? '请先生成模拟数据' : undefined}
          >
            <ICONS.trend size={14} />
            {backtestMut.isPending ? '回测中…' : '运行回测'}
          </button>
        </div>

        {prices.length > 0 && (
          <div style={{ marginTop: 12, color: 'var(--color-text-secondary)', fontSize: 'var(--text-sm)' }}>
            已加载 {prices.length} 个交易日模拟数据，价格区间：
            <span style={{ fontFamily: 'var(--font-mono)' }}>
              {' '}
              {Math.min(...prices).toFixed(2)} – {Math.max(...prices).toFixed(2)}
            </span>
          </div>
        )}
      </div>

      {/* Loading */}
      {(mockMut.isPending || backtestMut.isPending) && (
        <Loading text={backtestMut.isPending ? '正在运行回测…' : '正在生成模拟数据…'} />
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
              <span className="admin-card-title">净值曲线</span>
            </div>
            {equityData.length === 0 ? (
              <EmptyState title="暂无净值数据" icon="trend" />
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
                      formatter={(value) => [formatTick(Number(value)), '净值']}
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
              <span className="admin-card-title">交易记录（共 {result.trade_log.length} 条）</span>
            </div>
            {result.trade_log.length === 0 ? (
              <EmptyState title="暂无交易记录" icon="queries" />
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
