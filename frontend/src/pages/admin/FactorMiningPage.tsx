import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation } from '@tanstack/react-query'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as ReTooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'
import Loading from '../../components/ui/Loading.tsx'
import EmptyState from '../../components/ui/EmptyState.tsx'
import { toast } from '../../components/ui/Toaster.tsx'
import { ICONS } from '../../components/ui/Icons.tsx'
import { getErrorMessage } from '../../utils/errors.ts'
import {
  mineFactors,
  type FactorResult,
  type MineFactorsResponse,
} from '../../api/factorMining.ts'
import {
  CHART_TOOLTIP_STYLE,
  CHART_LABEL_STYLE,
  CHART_AXIS_TICK,
  CHART_AXIS_PROPS,
  CHART_GRID_PROPS,
  CHART_COLORS,
} from '../../components/charts/chartTokens.ts'

function buildDefaultFinancialData(companyA: string, companyB: string): string {
  return JSON.stringify(
    [
      { company: companyA, revenue: 1000, net_profit: 200, total_assets: 5000, pe: 15 },
      { company: companyB, revenue: 1200, net_profit: 180, total_assets: 4800, pe: 18 },
    ],
    null,
    2,
  )
}

function fmtPct(v: number): string {
  return `${(v * 100).toFixed(2)}%`
}

function fmtNum(v: number, digits = 4): string {
  if (!Number.isFinite(v)) return '—'
  return v.toFixed(digits)
}

export default function FactorMiningPage() {
  const { t } = useTranslation('adminFactorMining')
  const [financialDataText, setFinancialDataText] = useState(() =>
    buildDefaultFinancialData(t('input.exampleCompanyA'), t('input.exampleCompanyB')),
  )
  const [forwardReturnsText, setForwardReturnsText] = useState('')
  const [result, setResult] = useState<MineFactorsResponse | null>(null)

  const mineMut = useMutation({
    mutationFn: async () => {
      let financial_data: Array<Record<string, unknown>> = []
      try {
        const parsed = JSON.parse(financialDataText)
        if (!Array.isArray(parsed)) {
          throw new Error(t('errors.financialArrayRequired'))
        }
        financial_data = parsed as Array<Record<string, unknown>>
      } catch (e) {
        throw new Error(
          t('errors.financialParseFailed', {
            message: e instanceof Error ? e.message : String(e),
          }),
        )
      }

      let forward_returns: Record<string, number> | undefined
      if (forwardReturnsText.trim()) {
        try {
          const parsedFR = JSON.parse(forwardReturnsText)
          if (typeof parsedFR !== 'object' || parsedFR === null || Array.isArray(parsedFR)) {
            throw new Error(t('errors.forwardReturnsObjectRequired'))
          }
          forward_returns = parsedFR as Record<string, number>
        } catch (e) {
          throw new Error(
            t('errors.forwardReturnsParseFailed', {
              message: e instanceof Error ? e.message : String(e),
            }),
          )
        }
      }

      const res = await mineFactors({ financial_data, forward_returns })
      return res.data
    },
    onSuccess: (data) => {
      setResult(data)
      toast.success(
        t('toast.mineSuccess'),
        t('toast.mineSuccessDesc', { count: data.factors.length }),
      )
    },
    onError: (err) => {
      toast.error(t('toast.mineFailed'), getErrorMessage(err, t('errors.mineFailed')))
    },
  })

  const sortedFactors: FactorResult[] = useMemo(() => {
    if (!result?.factors) return []
    return [...result.factors].sort((a, b) => a.rank - b.rank)
  }, [result])

  const chartData = useMemo(
    () =>
      sortedFactors.map((f, idx) => ({
        name: f.name,
        ic: f.ic,
        color: CHART_COLORS[idx % CHART_COLORS.length],
      })),
    [sortedFactors],
  )

  const handleMine = () => {
    mineMut.mutate()
  }

  return (
    <div className="admin-model-management">
      {/* Header */}
      <div className="admin-page-header">
        <h1 className="admin-page-title">{t('title')}</h1>
        <p className="admin-page-desc">{t('description')}</p>
      </div>

      {/* Input */}
      <div className="admin-card">
        <div className="admin-card-header">
          <span className="admin-card-title">{t('input.title')}</span>
        </div>

        <div className="admin-form-row">
          <label className="admin-form-label">
            {t('input.financialData')}{' '}
            <span className="admin-form-hint">{t('input.financialDataHint')}</span>
          </label>
          <textarea
            className="admin-form-input"
            value={financialDataText}
            onChange={(e) => setFinancialDataText(e.target.value)}
            rows={8}
            placeholder={t('input.financialDataPlaceholder')}
            style={{ fontFamily: 'var(--font-mono)', minHeight: 180, resize: 'vertical' }}
          />
        </div>

        <div className="admin-form-row">
          <label className="admin-form-label">
            {t('input.forwardReturns')}{' '}
            <span className="admin-form-hint">{t('input.forwardReturnsHint')}</span>
          </label>
          <textarea
            className="admin-form-input"
            value={forwardReturnsText}
            onChange={(e) => setForwardReturnsText(e.target.value)}
            rows={4}
            placeholder={t('input.forwardReturnsPlaceholder')}
            style={{ fontFamily: 'var(--font-mono)', minHeight: 100, resize: 'vertical' }}
          />
        </div>

        {mineMut.isError && (
          <div className="admin-form-error">
            {getErrorMessage(mineMut.error, t('errors.mineFailed'))}
          </div>
        )}

        <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
          <button
            className="btn btn-primary"
            onClick={handleMine}
            disabled={mineMut.isPending}
          >
            <ICONS.trend size={14} />
            {mineMut.isPending ? t('actions.mining') : t('actions.mine')}
          </button>
          <button
            className="btn btn-secondary"
            onClick={() => {
              setResult(null)
              mineMut.reset()
            }}
            disabled={mineMut.isPending}
          >
            {t('actions.clear')}
          </button>
        </div>
      </div>

      {/* Results */}
      {mineMut.isPending && <Loading text={t('loading')} />}

      {!mineMut.isPending && result && (
        <>
          {/* Summary */}
          <div className="admin-card">
            <div className="admin-card-header">
              <span className="admin-card-title">{t('summary.title')}</span>
            </div>
            <p style={{ margin: 0, lineHeight: 1.7, color: 'var(--color-text-secondary)' }}>
              {result.summary || t('summary.empty')}
            </p>
            {result.best_factors.length > 0 && (
              <div style={{ marginTop: 12, display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {result.best_factors.map((f) => (
                  <span
                    key={f.name}
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: 6,
                      padding: '4px 10px',
                      borderRadius: 'var(--radius-sm)',
                      background: 'var(--color-primary-subtle)',
                      color: 'var(--color-primary)',
                      fontSize: 'var(--text-xs)',
                      fontWeight: 600,
                    }}
                  >
                    <ICONS.check size={12} />
                    {t('summary.bestFactor', { name: f.name, ic: fmtNum(f.ic, 3) })}
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* IC Chart */}
          <div className="admin-card">
            <div className="admin-card-header">
              <span className="admin-card-title">{t('chart.title')}</span>
            </div>
            {chartData.length === 0 ? (
              <EmptyState title={t('chart.empty')} icon="queries" />
            ) : (
              <div className="chart-container chart-container-lg">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData} margin={{ top: 8, right: 16, bottom: 8, left: 4 }}>
                    <CartesianGrid {...CHART_GRID_PROPS} />
                    <XAxis dataKey="name" tick={CHART_AXIS_TICK} {...CHART_AXIS_PROPS} />
                    <YAxis tick={CHART_AXIS_TICK} {...CHART_AXIS_PROPS} width={56} />
                    <ReTooltip
                      contentStyle={CHART_TOOLTIP_STYLE}
                      labelStyle={CHART_LABEL_STYLE}
                      cursor={{ fill: 'var(--color-primary-subtle)' }}
                      formatter={(value) => [fmtNum(Number(value), 4), t('chart.icLabel')]}
                    />
                    <Bar dataKey="ic" radius={[6, 6, 0, 0]} maxBarSize={48}>
                      {chartData.map((entry, idx) => (
                        <Cell key={`cell-${idx}`} fill={entry.color} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>

          {/* Factor Table */}
          <div className="admin-card">
            <div className="admin-card-header">
              <span className="admin-card-title">{t('table.title')}</span>
            </div>
            {sortedFactors.length === 0 ? (
              <EmptyState title={t('table.empty')} icon="queries" />
            ) : (
              <div className="admin-table-wrapper">
                <table className="admin-table">
                  <thead>
                    <tr>
                      <th style={{ width: 60, textAlign: 'center' }}>{t('table.rank')}</th>
                      <th>{t('table.name')}</th>
                      <th>{t('table.category')}</th>
                      <th style={{ width: 100, textAlign: 'right' }}>{t('table.ic')}</th>
                      <th style={{ width: 100, textAlign: 'right' }}>{t('table.ir')}</th>
                      <th style={{ width: 110, textAlign: 'right' }}>{t('table.winRate')}</th>
                      <th>{t('table.description')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortedFactors.map((f) => (
                      <tr key={`${f.name}-${f.rank}`}>
                        <td style={{ textAlign: 'center', fontWeight: 700 }}>{f.rank}</td>
                        <td className="admin-table-name">
                          <span className="admin-model-display">{f.name}</span>
                        </td>
                        <td>{f.category}</td>
                        <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)' }}>
                          {fmtNum(f.ic, 4)}
                        </td>
                        <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)' }}>
                          {fmtNum(f.ir, 4)}
                        </td>
                        <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)' }}>
                          {fmtPct(f.ic_win_rate)}
                        </td>
                        <td style={{ color: 'var(--color-text-secondary)' }}>{f.description}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
