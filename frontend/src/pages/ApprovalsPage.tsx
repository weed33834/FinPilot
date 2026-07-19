import { useEffect, useState } from 'react'
import { api } from '../api/client'
import Loading from '../components/ui/Loading.tsx'
import EmptyState from '../components/ui/EmptyState.tsx'
import Badge from '../components/ui/Badge.tsx'
import { getErrorMessage } from '../utils/errors.ts'
import { formatDateTime } from '../utils/format.ts'
import type { PendingApproval } from '../types/approval'
import type { DataResponse, PaginatedResponse, Report } from '../types/report'

interface ApprovalRecord {
  id: string
  report_id: string
  reviewer_id: string
  action: string
  comments: string | null
  created_at: string | null
}

const ACTION_LABELS: Record<string, string> = {
  approve: '通过',
  reject: '驳回',
  modify: '退回修改',
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
  const [pendingApprovals, setPendingApprovals] = useState<PendingApproval[]>([])
  const [history, setHistory] = useState<ApprovalRecord[]>([])
  const [loading, setLoading] = useState(false)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [error, setError] = useState('')
  const [comments, setComments] = useState<Record<string, string>>({})
  const [acting, setActing] = useState<Record<string, boolean>>({})

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
      setError(getErrorMessage(err, '加载待审批报告失败'))
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

  const handleAction = async (reportId: string, action: 'approve' | 'reject') => {
    setActing((prev) => ({ ...prev, [reportId]: true }))
    try {
      await api.post(`/approvals/${reportId}/action`, {
        action,
        comments: comments[reportId] || undefined,
      })
      setComments((prev) => ({ ...prev, [reportId]: '' }))
      await Promise.all([fetchPendingApprovals(), fetchHistory()])
    } catch (err) {
      setError(getErrorMessage(err, '审批操作失败'))
    } finally {
      setActing((prev) => ({ ...prev, [reportId]: false }))
    }
  }

  return (
    <div className="container">
      <div className="page-header">
        <div>
          <h1>人工审批</h1>
          <p className="text-muted text-sm">复核待审批报告，也能翻历史记录</p>
        </div>
        <button type="button" className="secondary" onClick={() => { fetchPendingApprovals(); fetchHistory() }}>
          刷新
        </button>
      </div>

      {error && (
        <div className="alert alert-error mb-4" role="alert">
          {error}
        </div>
      )}

      <div className="card">
        <h3 className="card-title">待审批报告</h3>
        {loading ? (
          <Loading text="加载待审批报告中..." />
        ) : pendingApprovals.length === 0 ? (
          <EmptyState title="暂无待审批报告" description="当有报告进入待审批状态时，将显示在这里。" />
        ) : (
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>报告</th>
                  <th>状态</th>
                  <th>提交时间</th>
                  <th>备注</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {pendingApprovals.map((approval) => (
                  <tr key={approval.id}>
                    <td>{approval.report_title}</td>
                    <td><Badge status="reviewing" label="待审批" /></td>
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
                        placeholder="审批备注（可选）"
                        aria-label="审批备注"
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
                          通过
                        </button>
                        <button
                          type="button"
                          className="secondary"
                          onClick={() => handleAction(approval.report_id, 'reject')}
                          disabled={acting[approval.report_id]}
                        >
                          驳回
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card">
        <h3 className="card-title">审核历史</h3>
        {historyLoading ? (
          <Loading text="加载审核历史..." />
        ) : history.length === 0 ? (
          <EmptyState title="暂无审核记录" description="已完成的审批将记录在这里。" />
        ) : (
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>报告 ID</th>
                  <th>审核人</th>
                  <th>动作</th>
                  <th>备注</th>
                  <th>时间</th>
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
                        label={ACTION_LABELS[record.action] || record.action}
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
