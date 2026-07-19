import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { adminApi } from '../../api/adminClient.ts'
import { ICONS } from '../../components/ui/Icons.tsx'
import { toast } from '../../components/ui/Toaster.tsx'
import { confirm } from '../../components/ui/ConfirmDialog.tsx'
import Loading from '../../components/ui/Loading.tsx'
import EmptyState from '../../components/ui/EmptyState.tsx'
import { getErrorMessage } from '../../utils/errors.ts'
import { formatDateTime } from '../../utils/format.ts'

// ==================== 类型定义 ====================

interface Nl2sqlStats {
  count: number
  avg_score: number
  avg_latency_ms: number
  sql_valid_rate: number
}

interface RagStats {
  count: number
  avg_score: number
  avg_mrr: number
  avg_ndcg: number
  avg_hit_rate: number
}

interface EvalStats {
  total: number
  nl2sql: Nl2sqlStats
  rag: RagStats
}

type EvalType = 'nl2sql' | 'rag'
type EvalTab = 'all' | EvalType

interface EvalRecord {
  id: string
  question: string
  eval_type: EvalType
  score: number
  eval_method: string
  created_at: string
}

interface EvalRecordsPage {
  items: EvalRecord[]
  total: number
  page: number
  page_size: number
}

/** 统一后端响应：{ code, message, data } */
interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

const PAGE_SIZE = 20

/** 将得分归一化到 0~1 区间，兼容 0~100 与 0~1 两种刻度。 */
function normalizeScore(score: number): number {
  if (score > 1) return score / 100
  return score
}

/** 按归一化得分返回颜色：高绿、中黄、低红。 */
function scoreColor(score: number): string {
  const n = normalizeScore(score)
  if (n >= 0.8) return 'var(--color-success)'
  if (n >= 0.5) return 'var(--color-warning)'
  return 'var(--color-danger)'
}

function formatScore(score: number | null | undefined): string {
  if (score === null || score === undefined || Number.isNaN(score)) return '—'
  return score.toFixed(3)
}

function formatRate(rate: number | null | undefined): string {
  if (rate === null || rate === undefined || Number.isNaN(rate)) return '—'
  return `${(normalizeScore(rate) * 100).toFixed(1)}%`
}

const TYPE_BADGE_CLASS: Record<EvalType, string> = {
  nl2sql: 'badge reviewing',
  rag: 'badge approved',
}

interface StatCardProps {
  icon: React.ReactNode
  iconVariant: string
  value: string
  label: string
  hint: string
  loading: boolean
}

function StatCard({ icon, iconVariant, value, label, hint, loading }: StatCardProps) {
  return (
    <div className="stat-card">
      <div className="stat-card-head">
        <div className={`stat-icon ${iconVariant}`}>{icon}</div>
      </div>
      <div className="stat-value">{loading ? '—' : value}</div>
      <div className="stat-label">{label}</div>
      <div className="stat-hint">{loading ? '—' : hint}</div>
    </div>
  )
}

export default function EvalManagement() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [tab, setTab] = useState<EvalTab>('all')
  const [page, setPage] = useState(1)

  // ---- 评估统计 ----
  const { data: stats, isLoading: statsLoading } = useQuery<EvalStats>({
    queryKey: ['eval-stats'],
    queryFn: async () => {
      const res = await adminApi.get<ApiResponse<EvalStats>>('/eval/stats')
      return res.data.data
    },
  })

  // ---- 评估记录（分页 + 类型筛选）----
  const { data: recordsData, isLoading: recordsLoading } = useQuery<EvalRecordsPage>({
    queryKey: ['eval-records', tab, page],
    queryFn: async () => {
      const params: Record<string, string | number> = { page, page_size: PAGE_SIZE }
      if (tab !== 'all') params.eval_type = tab
      const res = await adminApi.get<ApiResponse<EvalRecordsPage | EvalRecord[]>>(
        '/eval/records',
        { params },
      )
      const d = res.data.data
      // 兼容直接返回数组的情况
      if (Array.isArray(d)) {
        return { items: d, total: d.length, page: 1, page_size: PAGE_SIZE }
      }
      return d
    },
  })

  // ---- 删除记录 ----
  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      await adminApi.delete(`/eval/records/${id}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['eval-records'] })
      queryClient.invalidateQueries({ queryKey: ['eval-stats'] })
    },
  })

  const handleDelete = async (record: EvalRecord) => {
    const ok = await confirm({
      title: t('eval.deleteTitle'),
      message: t('eval.deleteMessage'),
      confirmText: t('common:actions.delete'),
      cancelText: t('common:actions.cancel'),
      variant: 'danger',
    })
    if (!ok) return
    try {
      await deleteMutation.mutateAsync(record.id)
      toast.success(t('eval.toastDeleted'))
    } catch (err) {
      toast.error(t('eval.toastDeleteFailed'), getErrorMessage(err))
    }
  }

  const handleTabChange = (next: EvalTab) => {
    setTab(next)
    setPage(1)
  }

  const records = recordsData?.items ?? []
  const total = recordsData?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  const tabs: { key: EvalTab; label: string }[] = [
    { key: 'all', label: t('eval.tabAll') },
    { key: 'nl2sql', label: t('eval.tabNl2sql') },
    { key: 'rag', label: t('eval.tabRag') },
  ]

  return (
    <div>
      <div className="admin-page-header">
        <h2 className="admin-page-title">{t('eval.title')}</h2>
        <p className="admin-page-subtitle">{t('eval.subtitle')}</p>
      </div>

      {/* 统计卡片 */}
      <div className="stat-grid">
        <StatCard
          icon={<ICONS.queries size={20} />}
          iconVariant="reports"
          label={t('eval.statNl2sqlScore')}
          value={formatScore(stats?.nl2sql.avg_score)}
          hint={
            stats
              ? `${stats.nl2sql.count} ${t('eval.unitRecords')} · ${formatRate(stats.nl2sql.sql_valid_rate)}`
              : '—'
          }
          loading={statsLoading}
        />
        <StatCard
          icon={<ICONS.documents size={20} />}
          iconVariant="documents"
          label={t('eval.statRagScore')}
          value={formatScore(stats?.rag.avg_score)}
          hint={
            stats
              ? `${stats.rag.count} ${t('eval.unitRecords')} · MRR ${formatScore(stats.rag.avg_mrr)}`
              : '—'
          }
          loading={statsLoading}
        />
        <StatCard
          icon={<ICONS.reports size={20} />}
          iconVariant="agent"
          label={t('eval.statTotal')}
          value={stats ? String(stats.total) : '—'}
          hint={stats ? `NL2SQL ${stats.nl2sql.count} · RAG ${stats.rag.count}` : '—'}
          loading={statsLoading}
        />
        <StatCard
          icon={<ICONS.check size={20} />}
          iconVariant="approvals"
          label={t('eval.statSqlValidRate')}
          value={formatRate(stats?.nl2sql.sql_valid_rate)}
          hint={stats ? `${t('eval.avgLatency')} ${Math.round(stats.nl2sql.avg_latency_ms)}ms` : '—'}
          loading={statsLoading}
        />
      </div>

      {/* 类型筛选 Tab */}
      <div className="tabs" role="tablist">
        {tabs.map((tabItem) => (
          <button
            key={tabItem.key}
            type="button"
            role="tab"
            aria-selected={tab === tabItem.key}
            className={`tab-item${tab === tabItem.key ? ' active' : ''}`}
            onClick={() => handleTabChange(tabItem.key)}
          >
            {tabItem.label}
          </button>
        ))}
      </div>

      {/* 记录表格 */}
      {recordsLoading ? (
        <Loading text={t('eval.loading')} />
      ) : records.length === 0 ? (
        <EmptyState icon="queries" title={t('eval.emptyTitle')} description={t('eval.emptyDesc')} />
      ) : (
        <div className="card">
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>{t('eval.colQuestion')}</th>
                  <th>{t('eval.colType')}</th>
                  <th>{t('eval.colScore')}</th>
                  <th>{t('eval.colMethod')}</th>
                  <th>{t('eval.colCreated')}</th>
                  <th>{t('eval.colActions')}</th>
                </tr>
              </thead>
              <tbody>
                {records.map((record) => {
                  const typeLabel =
                    record.eval_type === 'nl2sql' ? t('eval.typeNl2sql') : t('eval.typeRag')
                  const truncated =
                    record.question.length > 40
                      ? `${record.question.slice(0, 40)}…`
                      : record.question
                  return (
                    <tr key={record.id}>
                      <td title={record.question}>
                        {truncated || <span className="text-muted">—</span>}
                      </td>
                      <td>
                        <span className={TYPE_BADGE_CLASS[record.eval_type]}>{typeLabel}</span>
                      </td>
                      <td>
                        <span
                          style={{
                            color: scoreColor(record.score),
                            fontWeight: 600,
                            fontFamily: 'var(--font-mono)',
                          }}
                        >
                          {formatScore(record.score)}
                        </span>
                      </td>
                      <td>{record.eval_method || <span className="text-muted">—</span>}</td>
                      <td>{formatDateTime(record.created_at)}</td>
                      <td>
                        <div className="action-group">
                          <button
                            type="button"
                            className="danger"
                            onClick={() => handleDelete(record)}
                            disabled={deleteMutation.isPending}
                          >
                            <ICONS.close size={14} />
                            {t('common:actions.delete')}
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          {/* 分页 */}
          <div className="pagination">
            <button
              type="button"
              className="secondary"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              {t('eval.prevPage')}
            </button>
            <span className="text-sm">
              {t('eval.pageInfo', { page, total: totalPages, count: total })}
            </span>
            <button
              type="button"
              className="secondary"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
            >
              {t('eval.nextPage')}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
