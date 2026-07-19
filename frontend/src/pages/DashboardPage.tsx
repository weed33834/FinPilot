import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client.ts'
import { PageSkeleton } from '../components/ui/Loading.tsx'
import { ICONS } from '../components/ui/Icons.tsx'
import { getErrorMessage } from '../utils/errors.ts'
import { useAuth } from '../context/AuthContext.tsx'
import {
  DOCUMENT_STATUS_COLORS,
  REPORT_STATUS_COLORS,
  ROLE_TIP_KEYS,
  STATUS_LABELS,
  SUGGESTION_KEYS,
  type DashboardSummary,
} from './dashboard/constants.ts'
import {
  PendingTodoCard,
  ReportTrendChart,
  StatusDistributionChart,
  type ChartDatum,
} from './dashboard/DashboardCharts.tsx'
import {
  RecentActivitiesList,
  RecentDocumentsList,
  RecentReportsList,
} from './dashboard/DashboardLists.tsx'

export default function DashboardPage() {
  const { t } = useTranslation(['common', 'dashboard'])
  const { username, role } = useAuth()
  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const fetchSummary = async () => {
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
  }

  useEffect(() => {
    fetchSummary()
  }, [])

  const reportChartData: ChartDatum[] = useMemo(
    () =>
      summary
        ? Object.entries(summary.report_status_distribution || {}).map(([status, count]) => ({
            name: STATUS_LABELS[status] ? t(STATUS_LABELS[status]) : status,
            value: count,
            color: REPORT_STATUS_COLORS[status] || 'var(--color-text-muted)',
          }))
        : [],
    [summary, t],
  )

  const documentChartData: ChartDatum[] = useMemo(
    () =>
      summary
        ? Object.entries(summary.document_status_distribution || {}).map(([status, count]) => ({
            name: STATUS_LABELS[status] ? t(STATUS_LABELS[status]) : status,
            value: count,
            color: DOCUMENT_STATUS_COLORS[status] || 'var(--color-text-muted)',
          }))
        : [],
    [summary, t],
  )

  const pendingCount = summary?.pending_approval_count || 0
  const greetingKey = role ? `dashboard:greeting.${role}` : 'dashboard:greeting.viewer'
  const tipKey = ROLE_TIP_KEYS[role || 'viewer'] || ROLE_TIP_KEYS.viewer

  return (
    <div className="container">
      <div className="page-header">
        <div>
          <h1>{t('dashboard:title')}</h1>
          <p>
            {t(greetingKey, { username })}
          </p>
        </div>
        <button type="button" className="secondary" onClick={fetchSummary} aria-label={t('common:actions.refresh')}>
          <ICONS.refresh size={16} />
          {t('common:actions.refresh')}
        </button>
      </div>

      {error && (
        <div className="alert alert-error mb-4" role="alert">
          {error}
        </div>
      )}

      {loading ? (
        <PageSkeleton />
      ) : summary ? (
        <>
          {/* 实时数据条 */}
          <div className="data-ticker mb-4">
            <div className="data-ticker-item">
              <span className="data-ticker-label">报表</span>
              <span className="num-up">{summary.report_count}</span>
            </div>
            <div className="data-ticker-item">
              <span className="data-ticker-label">待审批</span>
              <span className={pendingCount ? 'num-up' : 'num-flat'}>{pendingCount}</span>
            </div>
            <div className="data-ticker-item">
              <span className="data-ticker-label">文档</span>
              <span>{summary.document_count}</span>
            </div>
            <div className="data-ticker-item">
              <span className="data-ticker-label">查询中</span>
              <span>{summary.processing_query_count ?? '-'}</span>
            </div>
          </div>

          {/* 顶部紧凑指标条 */}
          <div className="stat-grid compact">
            <Link to="/reports" className={`stat-card ${!summary.report_count ? 'is-zero' : ''}`}>
              <div className="stat-card-head">
                <div className="stat-icon reports">
                  <ICONS.reports size={20} />
                </div>
                <div className="stat-trend flat">—</div>
              </div>
              <div className="stat-value">{summary.report_count}</div>
              <div className="stat-label">{t('dashboard:stats.reports')}</div>
              <div className="stat-hint">
                {summary.approved_report_count ?? '-'} {t('dashboard:stats.approved')}
              </div>
            </Link>
            <Link to="/approvals" className={`stat-card ${!pendingCount ? 'is-zero' : ''}`}>
              <div className="stat-card-head">
                <div className="stat-icon approvals">
                  <ICONS.approvals size={20} />
                </div>
                <div className={`stat-trend ${pendingCount ? 'up' : 'flat'}`}>
                  {pendingCount ? 'NEW' : '—'}
                </div>
              </div>
              <div className="stat-value">{pendingCount}</div>
              <div className="stat-label">{t('dashboard:stats.pendingApprovals')}</div>
              <div className="stat-hint">
                {summary.total_approval_count ?? '-'} {t('dashboard:stats.total')}
              </div>
            </Link>
            <Link to="/documents" className={`stat-card ${!summary.document_count ? 'is-zero' : ''}`}>
              <div className="stat-card-head">
                <div className="stat-icon documents">
                  <ICONS.documents size={20} />
                </div>
                <div className="stat-trend flat">—</div>
              </div>
              <div className="stat-value">{summary.document_count}</div>
              <div className="stat-label">{t('dashboard:stats.documents')}</div>
              <div className="stat-hint">
                {summary.parsed_document_count ?? '-'} {t('dashboard:stats.parsed')}
              </div>
            </Link>
            <Link to="/agent" className="stat-card">
              <div className="stat-card-head">
                <div className="stat-icon agent">
                  <ICONS.agent size={20} />
                </div>
                <div className="stat-trend up">AI</div>
              </div>
              <div className="stat-value stat-value-text">{t('dashboard:stats.enter')}</div>
              <div className="stat-label">{t('dashboard:stats.agentQueries')}</div>
              <div className="stat-hint">
                {summary.today_query_count ?? '-'} {t('dashboard:stats.today')}
              </div>
            </Link>
          </div>

          {/* 第一排：7 天趋势 + 审批待办 */}
          <div className="dashboard-grid">
            <ReportTrendChart trend={summary.approval_trend} />
            <PendingTodoCard count={pendingCount} />
          </div>

          {/* 第二排：最近报告 + 最近文档 */}
          <div className="dashboard-grid">
            <RecentReportsList items={summary.recent_reports} />
            <RecentDocumentsList items={summary.recent_documents} />
          </div>

          {/* 第三排：状态分布 + 动态 */}
          <div className="dashboard-grid">
            <StatusDistributionChart
              title={t('dashboard:sections.reportStatus')}
              data={reportChartData}
              cellKeyPrefix="cell"
            />
            <StatusDistributionChart
              title={t('dashboard:sections.documentStatus')}
              data={documentChartData}
              cellKeyPrefix="cell-doc"
            />
            <RecentActivitiesList items={summary.recent_activities} />
          </div>

          {/* 收尾：智能问答入口 + 角色提示 */}
          <div className="dashboard-grid">
            <div className="card card-tip">
              <h3 className="card-title">{t('dashboard:sections.suggestions')}</h3>
              <div className="suggestion-chips">
                {SUGGESTION_KEYS.map((key) => {
                  const text = t(key)
                  return (
                    <Link key={key} to={`/agent?question=${encodeURIComponent(text)}`} className="chip">
                      {text}
                    </Link>
                  )
                })}
              </div>
            </div>
            <div className="card">
              <h3 className="card-title">{t('dashboard:sections.roleTip')}</h3>
              <p className="text-sm">{t(tipKey)}</p>
            </div>
          </div>
        </>
      ) : null}
    </div>
  )
}
