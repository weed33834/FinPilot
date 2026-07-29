import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../../api/client'
import { getErrorMessage } from '../../utils/errors'
import { useAuth } from '../../context/AuthContext'
import { ICONS } from '../../components/ui/Icons'
import KpiCard from '../../components/charts/KpiCard'
import {
  PendingTodoCard,
  ReportTrendChart,
  StatusDistributionChart,
  type ChartDatum,
} from '../dashboard/DashboardCharts'
import {
  RecentActivitiesList,
  RecentDocumentsList,
  RecentReportsList,
} from '../dashboard/DashboardLists'
import { REPORT_STATUS_COLORS, STATUS_LABELS, type DashboardSummary } from '../dashboard/constants'
import MobilePageHeader from '../../components/mobile/MobilePageHeader'

/**
 * 移动端仪表盘：单列卡片流（与桌面多栏网格完全不同的信息组织）。
 * 复用桌面 DashboardCharts / DashboardLists / KpiCard 等数据子组件，自管取数。
 */
export default function DashboardMobile() {
  const { t } = useTranslation(['common', 'dashboard'])
  const { username } = useAuth()
  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const fetchSummary = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const response = await api.get('/dashboard/summary')
      setSummary(response.data.data)
    } catch (err) {
      setError(getErrorMessage(err, t('dashboard:error.loadFailed')))
    } finally {
      setLoading(false)
    }
  }, [t])

  useEffect(() => {
    void fetchSummary()
  }, [fetchSummary])

  const pendingCount = summary?.pending_approval_count || 0
  const reportChartData: ChartDatum[] = useMemo(
    () =>
      summary
        ? Object.entries(summary.report_status_distribution || {}).map(([status, count]) => ({
            name: STATUS_LABELS[status] ? t(STATUS_LABELS[status]) : status,
            value: count,
            color: REPORT_STATUS_COLORS[status] || 'var(--color-text-muted)',
          }))
        : [],
    [summary, t]
  )

  const kpis = [
    { key: 'reports', label: t('dashboard:stats.reports'), value: summary?.report_count ?? null },
    { key: 'pending', label: t('dashboard:stats.pendingApprovals'), value: pendingCount || null },
    { key: 'documents', label: t('dashboard:stats.documents'), value: summary?.document_count ?? null },
    { key: 'queries', label: t('dashboard:stats.agentQueries'), value: summary?.today_query_count ?? null },
  ]

  return (
    <div className="mdash">
      <MobilePageHeader
        title={t('dashboard:title')}
        right={
          <button
            type="button"
            className="mdash__refresh"
            onClick={fetchSummary}
            aria-label={t('common:actions.refresh')}
          >
            <ICONS.refresh size={18} />
          </button>
        }
      />

      {error && (
        <div className="mdash__error" role="alert">
          <span>{error}</span>
          <button type="button" onClick={fetchSummary}>
            {t('common:actions.retry')}
          </button>
        </div>
      )}

      {loading ? (
        <div className="mdash__loading">{t('common:status.loading')}</div>
      ) : summary ? (
        <div className="mdash__body">
          <div className="mdash__kpis">
            {kpis.map((k) => (
              <KpiCard key={k.key} label={k.label} value={k.value} unit="" />
            ))}
          </div>
          <ReportTrendChart trend={summary.approval_trend} />
          <PendingTodoCard count={pendingCount} />
          <StatusDistributionChart
            title={t('dashboard:stats.reports')}
            data={reportChartData}
            cellKeyPrefix="report"
          />
          <RecentReportsList items={summary.recent_reports} />
          <RecentDocumentsList items={summary.recent_documents} />
          <RecentActivitiesList items={summary.recent_activities} />
        </div>
      ) : (
        <div className="mdash__empty">{username ? t('dashboard:greeting', { username }) : t('common:status.empty')}</div>
      )}
    </div>
  )
}
