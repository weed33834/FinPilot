import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import Loading from '../components/ui/Loading.tsx'
import EmptyState from '../components/ui/EmptyState.tsx'
import Badge from '../components/ui/Badge.tsx'
import { ICONS } from '../components/ui/Icons.tsx'
import { toast } from '../components/ui/Toaster.tsx'
import { getErrorMessage } from '../utils/errors.ts'
import { formatDateTime } from '../utils/format.ts'
import { useDevice } from '../context/DeviceContext'
import type { PendingApproval } from '../types/approval'
import type { DataResponse, PaginatedResponse, Report } from '../types/report'
import ApprovalsMobile from './mobile/ApprovalsMobile'

interface ApprovalRecord {
  id: string
  report_id: string
  reviewer_id: string
  action: string
  comments: string | null
  created_at: string | null
}

function toPendingApproval(report: Report): PendingApproval {
  return {
    id: report.id,
    report_id: report.id,
    report_title: report.title,
    status: 'reviewing',
    created_at: report.created_at,
  }
}

export default function ApprovalsPage() {
  const { t } = useTranslation()
  const { isMobile } = useDevice()
  if (isMobile) return <ApprovalsMobile />
  const [pendingApprovals, setPendingApprovals] = useState<PendingApproval[]>([])
  const [history, setHistory] = useState<ApprovalRecord[]>([])
  const [loading, setLoading] = useState(false)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [error, setError] = useState('')
  const [comments, setComments] = useState<Record<string, string>>({})
  const [acting, setActing] = useState<Record<string, boolean>>({})
  const [keyword, setKeyword] = useState('')

  const fetchPendingApprovals = async () => {
    setLoading(true)
    setError('')
    try {
      const response = await api.get<DataResponse<PaginatedResponse<Report>>>('/reports', {
        params: { status: 'reviewing' },
      })
      const payload = response.data?.data
      const reports = Array.isArray(payload) ? payload : payload?.items || []
      setPendingApprovals(reports.map(toPendingApproval))
    } catch (err) {
      setError(getErrorMessage(err, t('common:approvals.loadFailed')))
    } finally {
      setLoading(false)
    }
  }

  const fetchHistory = async () => {
    setHistoryLoading(true)
    try {
      const response = await api.get<DataResponse<ApprovalRecord[]>>('/approvals', {
        params: { limit: 50 },
      })
      const data = response.data.data
      setHistory(Array.isArray(data) ? data : [])
    } catch {
      // 历史加载失败不打断主流程
      setHistory([])
    } finally {
      setHistoryLoading(false)
    }
  }

  useEffect(() => {
    fetchPendingApprovals()
    fetchHistory()
  }, [])

  // 关键词过滤（客户端，按报告标题匹配）
  const filteredApprovals = useMemo(() => {
    const kw = keyword.trim().toLowerCase()
    if (!kw) return pendingApprovals
    return pendingApprovals.filter((a) => (a.report_title || '').toLowerCase().includes(kw))
  }, [pendingApprovals, keyword])

  const handleAction = async (reportId: string, action: 'approve' | 'reject') => {
    // 驳回必须填写原因
    if (action === 'reject' && !comments[reportId]?.trim()) {
      toast.warning(t('common:approvals.commentRequired'))
      return
    }
    setActing((prev) => ({ ...prev, [reportId]: true }))
    try {
      await api.post(`/approvals/${reportId}/action`, {
        action,
        comments: comments[reportId] || undefined,
      })
      setComments((prev) => ({ ...prev, [reportId]: '' }))
      toast.success(action === 'approve' ? t('common:approvals.toastApproved') : t('common:approvals.toastRejected'))
      await Promise.all([fetchPendingApprovals(), fetchHistory()])
    } catch (err) {
      toast.error(getErrorMessage(err, t('common:approvals.actionFailed')))
    } finally {
      setActing((prev) => ({ ...prev, [reportId]: false }))
    }
  }

  const actionLabel = (action: string) => {
    if (action === 'approve') return t('common:approvals.actionApprove')
    if (action === 'reject') return t('common:approvals.actionReject')
    if (action === 'modify') return t('common:approvals.actionModify')
    return action
  }

  return (
    <div className="container">
      <div className="page-header">
        <div>
          <h1>{t('common:approvals.title')}</h1>
          <p className="text-muted text-sm">{t('common:approvals.subtitle')}</p>
        </div>
        <button type="button" className="secondary" onClick={() => { fetchPendingApprovals(); fetchHistory() }}>
          {t('common:approvals.refresh')}
        </button>
      </div>

      {error && (
        <div className="alert alert-error mb-4" role="alert">
          <span>{error}</span>
          <button type="button" className="chat-error-retry" onClick={() => fetchPendingApprovals()}>
            {t('common:approvals.retry')}
          </button>
        </div>
      )}

      <div className="card">
        <div className="card-title-row">
          <h3 className="card-title">{t('common:approvals.pendingTitle')}</h3>
          {pendingApprovals.length > 0 && (
            <div className="search-inline">
              <ICONS.search size={14} />
              <input
                type="search"
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                placeholder={t('common:approvals.searchPlaceholder')}
                aria-label={t('common:approvals.searchPlaceholder')}
              />
            </div>
          )}
        </div>
        {loading ? (
          <Loading text={t('common:approvals.pendingLoading')} />
        ) : pendingApprovals.length === 0 ? (
          <EmptyState
            icon="approvals"
            title={t('common:approvals.emptyPendingTitle')}
            description={t('common:approvals.emptyPendingDesc')}
            action={
              <button type="button" className="secondary" onClick={() => fetchPendingApprovals()}>
                {t('common:approvals.refresh')}
              </button>
            }
          />
        ) : filteredApprovals.length === 0 ? (
          <EmptyState
            icon="search"
            title={t('common:approvals.emptySearchTitle')}
            description={t('common:approvals.emptySearchDesc')}
          />
        ) : (
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>{t('common:approvals.colReport')}</th>
                  <th>{t('common:approvals.colStatus')}</th>
                  <th>{t('common:approvals.colSubmittedAt')}</th>
                  <th>{t('common:approvals.colComment')}</th>
                  <th>{t('common:approvals.colActions')}</th>
                </tr>
              </thead>
              <tbody>
                {filteredApprovals.map((approval) => {
                  const commentEmpty = !comments[approval.report_id]?.trim()
                  return (
                    <tr key={approval.id}>
                      <td>{approval.report_title}</td>
                      <td><Badge status="reviewing" label={t('common:approvals.statusReviewing')} /></td>
                      <td>{formatDateTime(approval.created_at)}</td>
                      <td>
                        <input
                          value={comments[approval.report_id] || ''}
                          onChange={(e) =>
                            setComments((prev) => ({
                              ...prev,
                              [approval.report_id]: e.target.value,
                            }))
                          }
                          placeholder={t('common:approvals.commentPlaceholder')}
                          aria-label={t('common:approvals.colComment')}
                          disabled={acting[approval.report_id]}
                          className="full-width"
                        />
                      </td>
                      <td>
                        <div className="action-group">
                          <button
                            type="button"
                            onClick={() => handleAction(approval.report_id, 'approve')}
                            disabled={acting[approval.report_id]}
                          >
                            {t('common:approvals.approve')}
                          </button>
                          <button
                            type="button"
                            className="secondary"
                            onClick={() => handleAction(approval.report_id, 'reject')}
                            disabled={acting[approval.report_id] || commentEmpty}
                            title={commentEmpty ? t('common:approvals.commentRequired') : undefined}
                          >
                            {t('common:approvals.reject')}
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card">
        <h3 className="card-title">{t('common:approvals.historyTitle')}</h3>
        {historyLoading ? (
          <Loading text={t('common:approvals.historyLoading')} />
        ) : history.length === 0 ? (
          <EmptyState
            icon="approvals"
            title={t('common:approvals.emptyHistoryTitle')}
            description={t('common:approvals.emptyHistoryDesc')}
          />
        ) : (
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>{t('common:approvals.colReportId')}</th>
                  <th>{t('common:approvals.colReviewer')}</th>
                  <th>{t('common:approvals.colAction')}</th>
                  <th>{t('common:approvals.colComment')}</th>
                  <th>{t('common:approvals.colTime')}</th>
                </tr>
              </thead>
              <tbody>
                {history.map((record) => (
                  <tr key={record.id}>
                    <td>
                      <span className="text-sm">{record.report_id.slice(0, 8)}</span>
                    </td>
                    <td>{record.reviewer_id.slice(0, 8)}</td>
                    <td>
                      <Badge
                        status={record.action === 'approve' ? 'approved' : record.action === 'reject' ? 'rejected' : 'modify'}
                        label={actionLabel(record.action)}
                      />
                    </td>
                    <td>{record.comments || <span className="text-muted">—</span>}</td>
                    <td>
                      {formatDateTime(record.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
