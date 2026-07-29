import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../../api/client'
import { getErrorMessage } from '../../utils/errors'
import { formatDateTime } from '../../utils/format'
import type { PendingApproval } from '../../types/approval'
import type { DataResponse, PaginatedResponse, Report } from '../../types/report'
import { ICONS } from '../../components/ui/Icons'
import Badge from '../../components/ui/Badge'
import { toast } from '../../components/ui/Toaster'
import MobileCard from '../../components/mobile/MobileCard'
import '../../i18n/mobile'

interface ApprovalRecord {
  id: string
  report_id: string
  reviewer_id: string
  action: string
  comments: string | null
  created_at: string | null
}

/**
 * 移动端审批：单列待审卡片（标题 + 状态 + 批注 + 通过/驳回），下方历史记录。
 * 与桌面表格不同，移动端把每行审批动作内联到卡片上，拇指即可操作。
 */
export default function ApprovalsMobile() {
  const { t } = useTranslation(['common', 'mobile'])
  const [pending, setPending] = useState<PendingApproval[]>([])
  const [history, setHistory] = useState<ApprovalRecord[]>([])
  const [loading, setLoading] = useState(false)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [error, setError] = useState('')
  const [keyword, setKeyword] = useState('')
  const [comments, setComments] = useState<Record<string, string>>({})
  const [acting, setActing] = useState<Record<string, boolean>>({})

  const fetchPending = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const res = await api.get<DataResponse<PaginatedResponse<Report>>>('/reports', {
        params: { status: 'reviewing' },
      })
      const payload = res.data?.data
      const reports = Array.isArray(payload) ? payload : payload?.items || []
      setPending(
        reports.map((r) => ({
          id: r.id,
          report_id: r.id,
          report_title: r.title,
          status: 'reviewing',
          created_at: r.created_at,
        })),
      )
    } catch (err) {
      setError(getErrorMessage(err, t('common:approvals.loadFailed')))
    } finally {
      setLoading(false)
    }
  }, [t])

  const fetchHistory = useCallback(async () => {
    setHistoryLoading(true)
    try {
      const res = await api.get<DataResponse<ApprovalRecord[]>>('/approvals', {
        params: { limit: 50 },
      })
      const data = res.data.data
      setHistory(Array.isArray(data) ? data : [])
    } catch {
      setHistory([])
    } finally {
      setHistoryLoading(false)
    }
  }, [])

  useEffect(() => {
    void fetchPending()
    void fetchHistory()
  }, [fetchPending, fetchHistory])

  const filtered = useMemo(() => {
    const kw = keyword.trim().toLowerCase()
    if (!kw) return pending
    return pending.filter((a) => (a.report_title || '').toLowerCase().includes(kw))
  }, [pending, keyword])

  const handleAction = async (reportId: string, action: 'approve' | 'reject') => {
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
      toast.success(
        action === 'approve'
          ? t('common:approvals.toastApproved')
          : t('common:approvals.toastRejected'),
      )
      setComments((prev) => ({ ...prev, [reportId]: '' }))
      await Promise.all([fetchPending(), fetchHistory()])
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
    <div className="mapproval">
      <div className="mapproval__head">
        <span className="mapproval__count">
          {t('common:approvals.pendingTitle')} · {pending.length}
        </span>
        <button type="button" className="mapproval__refresh" onClick={() => void fetchPending()}>
          <ICONS.refresh size={16} />
        </button>
      </div>

      {error && (
        <div className="mapproval__error" role="alert">
          <span>{error}</span>
        </div>
      )}

      {pending.length > 0 && (
        <input
          className="mapproval__search"
          type="search"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          placeholder={t('common:approvals.searchPlaceholder')}
          aria-label={t('common:approvals.searchPlaceholder')}
        />
      )}

      {loading ? (
        <div className="mapproval__loading">{t('common:approvals.pendingLoading')}</div>
      ) : pending.length === 0 ? (
        <div className="mapproval__empty">
          <ICONS.approvals size={28} />
          <p>{t('common:approvals.emptyPendingDesc')}</p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="mapproval__empty">
          <p>{t('common:approvals.emptySearchDesc')}</p>
        </div>
      ) : (
        <div className="mapproval__list">
          {filtered.map((a) => {
            const commentEmpty = !comments[a.report_id]?.trim()
            const busy = acting[a.report_id]
            return (
              <MobileCard key={a.id} className="mapproval__card">
                <div className="mapproval__card-head">
                  <span className="mapproval__title">{a.report_title}</span>
                  <Badge status="reviewing" label={t('common:approvals.statusReviewing')} />
                </div>
                <div className="mapproval__meta">
                  {a.created_at ? formatDateTime(a.created_at) : ''}
                </div>
                <input
                  className="mapproval__comment"
                  value={comments[a.report_id] || ''}
                  onChange={(e) =>
                    setComments((prev) => ({ ...prev, [a.report_id]: e.target.value }))
                  }
                  placeholder={t('common:approvals.commentPlaceholder')}
                  aria-label={t('common:approvals.colComment')}
                  disabled={busy}
                />
                <div className="mapproval__actions">
                  <button
                    type="button"
                    className="mapproval__approve"
                    onClick={() => void handleAction(a.report_id, 'approve')}
                    disabled={busy}
                  >
                    <ICONS.check size={16} />
                    {t('common:approvals.approve')}
                  </button>
                  <button
                    type="button"
                    className="mapproval__reject"
                    onClick={() => void handleAction(a.report_id, 'reject')}
                    disabled={busy || commentEmpty}
                    title={commentEmpty ? t('common:approvals.commentRequired') : undefined}
                  >
                    <ICONS.close size={16} />
                    {t('common:approvals.reject')}
                  </button>
                </div>
              </MobileCard>
            )
          })}
        </div>
      )}

      <div className="mapproval__history">
        <h3 className="mapproval__history-title">{t('common:approvals.historyTitle')}</h3>
        {historyLoading ? (
          <div className="mapproval__loading">{t('common:approvals.historyLoading')}</div>
        ) : history.length === 0 ? (
          <div className="mapproval__empty">
            <p>{t('common:approvals.emptyHistoryDesc')}</p>
          </div>
        ) : (
          <ul className="mapproval__history-list">
            {history.map((record) => (
              <li key={record.id} className="mapproval__history-item">
                <div className="mapproval__history-row">
                  <span className="mapproval__history-id">
                    {record.report_id.slice(0, 8)}
                  </span>
                  <Badge
                    status={
                      record.action === 'approve'
                        ? 'approved'
                        : record.action === 'reject'
                          ? 'rejected'
                          : 'modify'
                    }
                    label={actionLabel(record.action)}
                  />
                </div>
                <div className="mapproval__meta">{formatDateTime(record.created_at)}</div>
                {record.comments && (
                  <div className="mapproval__history-comment">{record.comments}</div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
