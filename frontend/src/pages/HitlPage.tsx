import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { adminApi } from '../api/adminClient.ts'
import { ICONS } from '../components/ui/Icons.tsx'
import { toast } from '../components/ui/Toaster.tsx'
import { confirm } from '../components/ui/ConfirmDialog.tsx'
import Modal from '../components/ui/Modal.tsx'
import Loading from '../components/ui/Loading.tsx'
import EmptyState from '../components/ui/EmptyState.tsx'
import { getErrorMessage } from '../utils/errors.ts'
import { formatDateTime } from '../utils/format.ts'

// ==================== 类型定义 ====================

type HitlStatus = 'pending' | 'approved' | 'rejected'
type HitlRisk = 'low' | 'medium' | 'high'
type HitlTab = 'pending' | 'approved' | 'rejected' | 'all'

interface HitlStats {
  total: number
  pending: number
  approved: number
  rejected: number
  high_risk_pending: number
}

interface HitlRequest {
  id: string
  action_type: string
  description: string
  risk_level: HitlRisk
  action_params: Record<string, unknown> | string | null
  status: HitlStatus
  created_at: string
  // 详情接口可能携带的扩展字段
  requested_by?: string | null
  resolved_by?: string | null
  comment?: string | null
  resolved_at?: string | null
  context?: Record<string, unknown> | string | null
}

/** 统一后端响应：{ code, message, data } */
interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

const RISK_BADGE_CLASS: Record<HitlRisk, string> = {
  low: 'badge success',
  medium: 'badge modify',
  high: 'badge failed',
}

const STATUS_BADGE_CLASS: Record<HitlStatus, string> = {
  pending: 'badge pending',
  approved: 'badge approved',
  rejected: 'badge rejected',
}

/** 卡片头部布局：左侧徽章组，右侧时间，窄屏自动换行。 */
const CARD_HEAD_STYLE: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  gap: 'var(--space-2)',
  flexWrap: 'wrap',
  marginBottom: 'var(--space-3)',
}

/** 安全地把 action_params / context 序列化为可读 JSON 字符串。 */
function toJsonString(
  value: Record<string, unknown> | string | null | undefined,
): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

export default function HitlPage() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [tab, setTab] = useState<HitlTab>('pending')
  const [comments, setComments] = useState<Record<string, string>>({})
  const [actingId, setActingId] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  // ---- 统计 ----
  const { data: stats, isLoading: statsLoading } = useQuery<HitlStats>({
    queryKey: ['hitl-stats'],
    queryFn: async () => {
      const res = await adminApi.get<ApiResponse<HitlStats>>('/hitl/stats')
      return res.data.data
    },
  })

  // ---- 列表 ----
  const { data: requests = [], isLoading: listLoading } = useQuery<HitlRequest[]>({
    queryKey: ['hitl-requests', tab],
    queryFn: async () => {
      const params: Record<string, string> = {}
      if (tab !== 'all') params.status_filter = tab
      const res = await adminApi.get<ApiResponse<HitlRequest[] | { items: HitlRequest[] }>>(
        '/hitl',
        { params },
      )
      const d = res.data.data
      // 兼容直接返回数组与 { items } 两种形态
      if (Array.isArray(d)) return d
      return d.items ?? []
    },
  })

  // ---- 详情（打开 Modal 时按需拉取）----
  const { data: detail, isLoading: detailLoading } = useQuery<HitlRequest | null>({
    queryKey: ['hitl-detail', selectedId],
    queryFn: async () => {
      const res = await adminApi.get<ApiResponse<HitlRequest>>(`/hitl/${selectedId}`)
      return res.data.data ?? null
    },
    enabled: !!selectedId,
  })

  // ---- 审批操作 ----
  const actionMutation = useMutation({
    mutationFn: async (vars: {
      id: string
      action: 'approve' | 'reject'
      comment: string
    }) => {
      await adminApi.post(`/hitl/${vars.id}/action`, {
        action: vars.action,
        comment: vars.comment,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['hitl-requests'] })
      queryClient.invalidateQueries({ queryKey: ['hitl-stats'] })
      queryClient.invalidateQueries({ queryKey: ['hitl-detail'] })
    },
  })

  const handleAction = async (req: HitlRequest, action: 'approve' | 'reject') => {
    const isApprove = action === 'approve'
    const ok = await confirm({
      title: isApprove ? t('hitl.approveTitle') : t('hitl.rejectTitle'),
      message: isApprove ? t('hitl.approveMessage') : t('hitl.rejectMessage'),
      confirmText: isApprove ? t('hitl.approve') : t('hitl.reject'),
      cancelText: t('common:actions.cancel'),
      variant: isApprove ? 'info' : 'danger',
    })
    if (!ok) return
    setActingId(req.id)
    try {
      await actionMutation.mutateAsync({
        id: req.id,
        action,
        comment: comments[req.id] || '',
      })
      setComments((prev) => {
        const next = { ...prev }
        delete next[req.id]
        return next
      })
      toast.success(isApprove ? t('hitl.toastApproved') : t('hitl.toastRejected'))
    } catch (err) {
      toast.error(t('hitl.toastActionFailed'), getErrorMessage(err))
    } finally {
      setActingId(null)
    }
  }

  const handleRefresh = () => {
    queryClient.invalidateQueries({ queryKey: ['hitl-requests'] })
    queryClient.invalidateQueries({ queryKey: ['hitl-stats'] })
  }

  const tabs: { key: HitlTab; label: string }[] = [
    { key: 'pending', label: t('hitl.tabPending') },
    { key: 'approved', label: t('hitl.tabApproved') },
    { key: 'rejected', label: t('hitl.tabRejected') },
    { key: 'all', label: t('hitl.tabAll') },
  ]

  const riskLabel = (r: HitlRisk): string =>
    r === 'low' ? t('hitl.riskLow') : r === 'medium' ? t('hitl.riskMedium') : t('hitl.riskHigh')
  const statusLabel = (s: HitlStatus): string =>
    s === 'pending'
      ? t('hitl.statusPending')
      : s === 'approved'
        ? t('hitl.statusApproved')
        : t('hitl.statusRejected')

  return (
    <div className="container">
      <div className="page-header">
        <div>
          <h1>{t('hitl.title')}</h1>
          <p className="text-muted text-sm">{t('hitl.subtitle')}</p>
        </div>
        <div className="action-group">
          <span className="badge pending">
            {t('hitl.statPending')}: {statsLoading ? '…' : stats?.pending ?? 0}
          </span>
          <span className="badge failed">
            {t('hitl.statHighRisk')}: {statsLoading ? '…' : stats?.high_risk_pending ?? 0}
          </span>
          <button type="button" className="secondary" onClick={handleRefresh}>
            <ICONS.refresh size={16} />
            {t('common:actions.refresh')}
          </button>
        </div>
      </div>

      {/* 状态筛选 Tab */}
      <div className="tabs" role="tablist">
        {tabs.map((tabItem) => (
          <button
            key={tabItem.key}
            type="button"
            role="tab"
            aria-selected={tab === tabItem.key}
            className={`tab-item${tab === tabItem.key ? ' active' : ''}`}
            onClick={() => setTab(tabItem.key)}
          >
            {tabItem.label}
          </button>
        ))}
      </div>

      {/* 列表 */}
      {listLoading ? (
        <Loading text={t('hitl.loading')} />
      ) : requests.length === 0 ? (
        <EmptyState icon="approvals" title={t('hitl.emptyTitle')} description={t('hitl.emptyDesc')} />
      ) : (
        <div>
          {requests.map((req) => {
            const paramsJson = toJsonString(req.action_params)
            const canAct = req.status === 'pending'
            const busy = actingId === req.id
            return (
              <div className="card" key={req.id}>
                <div style={CARD_HEAD_STYLE}>
                  <div className="action-group">
                    <span className="badge reviewing">{req.action_type}</span>
                    <span className={RISK_BADGE_CLASS[req.risk_level]}>
                      {t('hitl.colRiskLevel')}: {riskLabel(req.risk_level)}
                    </span>
                    <span className={STATUS_BADGE_CLASS[req.status]}>{statusLabel(req.status)}</span>
                  </div>
                  <span className="text-muted text-sm">{formatDateTime(req.created_at)}</span>
                </div>

                <p style={{ margin: '0 0 var(--space-3)' }}>
                  {req.description || <span className="text-muted">—</span>}
                </p>

                {paramsJson && (
                  <div className="detail-group">
                    <span className="detail-label">{t('hitl.colParams')}</span>
                    <pre className="code-block">{paramsJson}</pre>
                  </div>
                )}

                {canAct && (
                  <div className="form-group">
                    <input
                      className="full-width"
                      value={comments[req.id] || ''}
                      onChange={(e) =>
                        setComments((prev) => ({ ...prev, [req.id]: e.target.value }))
                      }
                      placeholder={t('hitl.commentPlaceholder')}
                      aria-label={t('hitl.commentPlaceholder')}
                      disabled={busy}
                    />
                  </div>
                )}

                <div className="action-group">
                  <button
                    type="button"
                    className="btn-success"
                    onClick={() => handleAction(req, 'approve')}
                    disabled={!canAct || busy}
                  >
                    <ICONS.check size={14} />
                    {t('hitl.approve')}
                  </button>
                  <button
                    type="button"
                    className="danger"
                    onClick={() => handleAction(req, 'reject')}
                    disabled={!canAct || busy}
                  >
                    <ICONS.close size={14} />
                    {t('hitl.reject')}
                  </button>
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => setSelectedId(req.id)}
                  >
                    {t('hitl.detail')}
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* 详情 Modal */}
      {selectedId && (
        <Modal
          title={t('hitl.detailTitle')}
          onClose={() => setSelectedId(null)}
          footer={
            <button type="button" className="secondary" onClick={() => setSelectedId(null)}>
              {t('common:actions.close')}
            </button>
          }
        >
          {detailLoading || !detail ? (
            <Loading text={t('hitl.loading')} />
          ) : (
            <>
              <div className="detail-group">
                <span className="detail-label">{t('hitl.colActionType')}</span>
                <p>
                  <span className="badge reviewing">{detail.action_type}</span>{' '}
                  <span className={RISK_BADGE_CLASS[detail.risk_level]}>
                    {t('hitl.colRiskLevel')}: {riskLabel(detail.risk_level)}
                  </span>{' '}
                  <span className={STATUS_BADGE_CLASS[detail.status]}>
                    {statusLabel(detail.status)}
                  </span>
                </p>
              </div>
              <div className="detail-group">
                <span className="detail-label">{t('hitl.colDescription')}</span>
                <p>{detail.description || <span className="text-muted">—</span>}</p>
              </div>
              <div className="detail-group">
                <span className="detail-label">{t('hitl.colCreated')}</span>
                <p>{formatDateTime(detail.created_at)}</p>
              </div>
              {detail.requested_by && (
                <div className="detail-group">
                  <span className="detail-label">{t('hitl.requestedBy')}</span>
                  <p>{detail.requested_by}</p>
                </div>
              )}
              {detail.resolved_by && (
                <div className="detail-group">
                  <span className="detail-label">{t('hitl.resolvedBy')}</span>
                  <p>{detail.resolved_by}</p>
                </div>
              )}
              {detail.resolved_at && (
                <div className="detail-group">
                  <span className="detail-label">{t('hitl.resolvedAt')}</span>
                  <p>{formatDateTime(detail.resolved_at)}</p>
                </div>
              )}
              {detail.comment && (
                <div className="detail-group">
                  <span className="detail-label">{t('hitl.comment')}</span>
                  <p>{detail.comment}</p>
                </div>
              )}
              <div className="detail-group">
                <span className="detail-label">{t('hitl.colParams')}</span>
                <pre className="code-block">
                  {toJsonString(detail.action_params) || <span className="text-muted">—</span>}
                </pre>
              </div>
              {detail.context && (
                <div className="detail-group">
                  <span className="detail-label">{t('hitl.context')}</span>
                  <pre className="code-block">{toJsonString(detail.context)}</pre>
                </div>
              )}
            </>
          )}
        </Modal>
      )}
    </div>
  )
}
