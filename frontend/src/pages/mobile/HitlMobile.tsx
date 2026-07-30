import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { adminApi } from '../../api/adminClient'
import { getErrorMessage } from '../../utils/errors'
import { formatDateTime } from '../../utils/format'
import { ICONS } from '../../components/ui/Icons'
import { toast } from '../../components/ui/Toaster'
import MobileCard from '../../components/mobile/MobileCard'
import BottomSheet from '../../components/mobile/BottomSheet'
import '../../i18n/mobile'

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
  requested_by?: string | null
  resolved_by?: string | null
  comment?: string | null
  resolved_at?: string | null
  context?: Record<string, unknown> | string | null
}

interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

const RISK_CLASS: Record<HitlRisk, string> = {
  low: 'badge success',
  medium: 'badge modify',
  high: 'badge failed',
}

const STATUS_CLASS: Record<HitlStatus, string> = {
  pending: 'badge pending',
  approved: 'badge approved',
  rejected: 'badge rejected',
}

function toJsonString(value: Record<string, unknown> | string | null | undefined): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

/**
 * 移动端人工审批（HITL）：状态概览 + 状态筛选 Tab + 请求卡片（风险/状态/批注/通过驳回）
 * + 底部弹层详情。与桌面一致的接口与状态机，仅交互层重排为单列触屏布局。
 */
export default function HitlMobile() {
  const { t } = useTranslation(['common', 'mobile'])
  const queryClient = useQueryClient()
  const [tab, setTab] = useState<HitlTab>('pending')
  const [comments, setComments] = useState<Record<string, string>>({})
  const [actingId, setActingId] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const { data: stats, isLoading: statsLoading } = useQuery<HitlStats>({
    queryKey: ['hitl-stats'],
    queryFn: async () => {
      const res = await adminApi.get<ApiResponse<HitlStats>>('/hitl/stats')
      return res.data.data
    },
  })

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
      if (Array.isArray(d)) return d
      return d.items ?? []
    },
  })

  const { data: detail, isLoading: detailLoading } = useQuery<HitlRequest | null>({
    queryKey: ['hitl-detail', selectedId],
    queryFn: async () => {
      const res = await adminApi.get<ApiResponse<HitlRequest>>(`/hitl/${selectedId}`)
      return res.data.data ?? null
    },
    enabled: !!selectedId,
  })

  const actionMutation = useMutation({
    mutationFn: async (vars: { id: string; action: 'approve' | 'reject'; comment: string }) => {
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
    setActingId(req.id)
    try {
      await actionMutation.mutateAsync({ id: req.id, action, comment: comments[req.id] || '' })
      setComments((prev) => {
        const next = { ...prev }
        delete next[req.id]
        return next
      })
      toast.success(action === 'approve' ? t('hitl.toastApproved') : t('hitl.toastRejected'))
    } catch (err) {
      toast.error(t('hitl.toastActionFailed'), getErrorMessage(err))
    } finally {
      setActingId(null)
    }
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
    <div className="mhitl">
      <div className="mhitl__stats">
        <span className="badge pending">
          {t('hitl.statPending')}: {statsLoading ? '…' : stats?.pending ?? 0}
        </span>
        <span className="badge failed">
          {t('hitl.statHighRisk')}: {statsLoading ? '…' : stats?.high_risk_pending ?? 0}
        </span>
      </div>

      <div className="mhitl__tabs" role="tablist">
        {tabs.map((tabItem) => (
          <button
            key={tabItem.key}
            type="button"
            role="tab"
            aria-selected={tab === tabItem.key}
            className={`mhitl__tab${tab === tabItem.key ? ' is-active' : ''}`}
            onClick={() => setTab(tabItem.key)}
          >
            {tabItem.label}
          </button>
        ))}
      </div>

      {listLoading ? (
        <div className="mhitl__loading">{t('hitl.loading')}</div>
      ) : requests.length === 0 ? (
        <div className="mhitl__empty">
          <ICONS.audit size={28} />
          <p>{t('hitl.emptyDesc')}</p>
        </div>
      ) : (
        <div className="mhitl__list">
          {requests.map((req) => {
            const paramsJson = toJsonString(req.action_params)
            const canAct = req.status === 'pending'
            const busy = actingId === req.id
            return (
              <MobileCard key={req.id} className="mhitl__card">
                <div className="mhitl__card-head">
                  <span className={RISK_CLASS[req.risk_level]}>
                    {t('hitl.colRiskLevel')}: {riskLabel(req.risk_level)}
                  </span>
                  <span className={STATUS_CLASS[req.status]}>{statusLabel(req.status)}</span>
                </div>
                <div className="mhitl__type">{req.action_type}</div>
                <p className="mhitl__desc">{req.description || '—'}</p>
                {paramsJson && (
                  <details className="mhitl__params-details">
                    <summary>{t('hitl.colParams')}</summary>
                    <pre className="mhitl__params">{paramsJson}</pre>
                  </details>
                )}
                {canAct && (
                  <input
                    className="mhitl__comment"
                    value={comments[req.id] || ''}
                    onChange={(e) => setComments((prev) => ({ ...prev, [req.id]: e.target.value }))}
                    placeholder={t('hitl.commentPlaceholder')}
                    aria-label={t('hitl.commentPlaceholder')}
                    disabled={busy}
                  />
                )}
                <div className="mhitl__actions">
                  <button
                    type="button"
                    className="mhitl__approve"
                    onClick={() => void handleAction(req, 'approve')}
                    disabled={!canAct || busy}
                  >
                    <ICONS.check size={16} />
                    {t('hitl.approve')}
                  </button>
                  <button
                    type="button"
                    className="mhitl__reject"
                    onClick={() => void handleAction(req, 'reject')}
                    disabled={!canAct || busy}
                  >
                    <ICONS.close size={16} />
                    {t('hitl.reject')}
                  </button>
                  <button
                    type="button"
                    className="mhitl__detail"
                    onClick={() => setSelectedId(req.id)}
                  >
                    {t('hitl.detail')}
                  </button>
                </div>
              </MobileCard>
            )
          })}
        </div>
      )}

      <BottomSheet
        open={!!selectedId}
        onClose={() => setSelectedId(null)}
        title={t('hitl.detailTitle')}
      >
        {detailLoading || !detail ? (
          <div className="mhitl__loading">{t('hitl.loading')}</div>
        ) : (
          <div className="mhitl__detail">
            <div className="mhitl__detail-row">
              <span className="mhitl__detail-label">{t('hitl.colActionType')}</span>
              <span className={RISK_CLASS[detail.risk_level]}>
                {detail.action_type} · {riskLabel(detail.risk_level)}
              </span>
            </div>
            <div className="mhitl__detail-row">
              <span className="mhitl__detail-label">{t('hitl.colDescription')}</span>
              <span>{detail.description || '—'}</span>
            </div>
            <div className="mhitl__detail-row">
              <span className="mhitl__detail-label">{t('hitl.colCreated')}</span>
              <span>{formatDateTime(detail.created_at)}</span>
            </div>
            {detail.requested_by && (
              <div className="mhitl__detail-row">
                <span className="mhitl__detail-label">{t('hitl.requestedBy')}</span>
                <span>{detail.requested_by}</span>
              </div>
            )}
            {detail.resolved_by && (
              <div className="mhitl__detail-row">
                <span className="mhitl__detail-label">{t('hitl.resolvedBy')}</span>
                <span>{detail.resolved_by}</span>
              </div>
            )}
            {detail.resolved_at && (
              <div className="mhitl__detail-row">
                <span className="mhitl__detail-label">{t('hitl.resolvedAt')}</span>
                <span>{formatDateTime(detail.resolved_at)}</span>
              </div>
            )}
            {detail.comment && (
              <div className="mhitl__detail-row">
                <span className="mhitl__detail-label">{t('hitl.comment')}</span>
                <span>{detail.comment}</span>
              </div>
            )}
            <div className="mhitl__detail-row">
              <span className="mhitl__detail-label">{t('hitl.colParams')}</span>
              <details className="mhitl__params-details" open>
                <summary>展开 / 收起</summary>
                <pre className="mhitl__params">{toJsonString(detail.action_params) || '—'}</pre>
              </details>
            </div>
            {detail.context && (
              <div className="mhitl__detail-row">
                <span className="mhitl__detail-label">{t('hitl.context')}</span>
                <pre className="mhitl__params">{toJsonString(detail.context)}</pre>
              </div>
            )}
          </div>
        )}
      </BottomSheet>
    </div>
  )
}
