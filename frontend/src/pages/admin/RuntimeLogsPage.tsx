import { useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Trans, useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import Modal from '../../components/ui/Modal.tsx'
import Loading from '../../components/ui/Loading.tsx'
import EmptyState from '../../components/ui/EmptyState.tsx'
import { confirm } from '../../components/ui/ConfirmDialog.tsx'
import { toast } from '../../components/ui/Toaster.tsx'
import { ICONS } from '../../components/ui/Icons.tsx'
import { getErrorMessage } from '../../utils/errors.ts'
import {
  batchDeleteRuntimeLogs,
  deleteRuntimeLog,
  exportRuntimeLogs,
  getConversationsSummary,
  getModuleStatus,
  getRuntimeLogDetail,
  getRuntimeStats,
  listRuntimeLogs,
  parsePayloadJson,
  type RuntimeLogItem,
  type RuntimeLogListParams,
} from '../../api/runtimeLogs.ts'

type Tab = 'stats' | 'logs' | 'conversations' | 'modules'

/* 筛选选项 value 列表（label 走 i18n，在组件内构建） */
function categoryOptions(t: TFunction) {
  return [
    { value: '', label: t('filters.allCategories') },
    { value: 'api', label: t('filters.categories.api') },
    { value: 'llm', label: t('filters.categories.llm') },
    { value: 'tool', label: t('filters.categories.tool') },
    { value: 'mcp', label: t('filters.categories.mcp') },
    { value: 'agent', label: t('filters.categories.agent') },
    { value: 'conversation', label: t('filters.categories.conversation') },
    { value: 'workflow', label: t('filters.categories.workflow') },
    { value: 'sandbox', label: t('filters.categories.sandbox') },
    { value: 'auth', label: t('filters.categories.auth') },
  ]
}

function levelOptions(t: TFunction) {
  return [
    { value: '', label: t('filters.allLevels') },
    { value: 'debug', label: t('filters.levels.debug') },
    { value: 'info', label: t('filters.levels.info') },
    { value: 'warning', label: t('filters.levels.warning') },
    { value: 'error', label: t('filters.levels.error') },
    { value: 'critical', label: t('filters.levels.critical') },
  ]
}

function statusOptions(t: TFunction) {
  return [
    { value: '', label: t('filters.allStatus') },
    { value: 'true', label: t('filters.status.success') },
    { value: 'false', label: t('filters.status.failed') },
  ]
}

/* ------------------------------------------------------------------ */
/*  辅助                                                                */
/* ------------------------------------------------------------------ */

const LEVEL_META: Record<string, { label: string; color: string; bg: string }> = {
  debug: { label: 'DEBUG', color: '#9aa', bg: 'rgba(127,127,127,.18)' },
  info: { label: 'INFO', color: '#3b82f6', bg: 'rgba(59,130,246,.15)' },
  warning: { label: 'WARN', color: '#eab308', bg: 'rgba(234,179,8,.15)' },
  error: { label: 'ERROR', color: '#ef4444', bg: 'rgba(239,68,68,.15)' },
  critical: { label: 'CRIT', color: '#a855f7', bg: 'rgba(168,85,247,.18)' },
}

function levelMeta(level: string) {
  return (
    LEVEL_META[String(level || '').toLowerCase()] || {
      label: level || '-',
      color: '#9aa',
      bg: 'rgba(127,127,127,.15)',
    }
  )
}

function fmtTime(v: string | null): string {
  if (!v) return '-'
  const d = new Date(String(v))
  if (Number.isNaN(d.getTime())) return String(v)
  return d.toLocaleString()
}

function fmtDuration(v: number | null): string {
  if (v == null) return '-'
  if (v < 1000) return `${Math.round(v)} ms`
  return `${(v / 1000).toFixed(2)} s`
}

function truncate(v: string | null, max = 80): string {
  if (!v) return '-'
  return v.length > max ? v.slice(0, max) + '…' : v
}

/* 统计卡片 */
function StatCard({
  label,
  value,
  hint,
  accent,
}: {
  label: string
  value: string | number
  hint?: string
  accent?: string
}) {
  return (
    <div className="admin-card" style={{ marginBottom: 0, padding: 'var(--space-4)' }}>
      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', marginBottom: 4 }}>
        {label}
      </div>
      <div
        style={{
          fontFamily: 'var(--font-display)',
          fontSize: 'var(--text-lg)',
          fontWeight: 700,
          color: accent ?? 'var(--color-text)',
        }}
      >
        {value}
      </div>
      {hint && (
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', marginTop: 2 }}>
          {hint}
        </div>
      )}
    </div>
  )
}

/* 横向 bar：data = [{label, value}] */
function BarList({ data }: { data: Array<{ label: string; value: number }> }) {
  const { t } = useTranslation('adminRuntimeLogs')
  if (data.length === 0) {
    return <EmptyState title={t('empty.noData')} size="sm" />
  }
  const max = Math.max(...data.map((d) => d.value), 1)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {data.map((d) => {
        const pct = Math.max(2, Math.round((d.value / max) * 100))
        return (
          <div key={d.label} style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: '0.8rem' }}>
            <div
              style={{
                width: 140,
                flexShrink: 0,
                color: 'var(--color-text-secondary)',
                fontFamily: 'var(--font-mono, monospace)',
                fontSize: '0.74rem',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
              title={d.label}
            >
              {d.label}
            </div>
            <div style={{ flex: 1, height: 10, background: 'var(--color-surface-raised)', borderRadius: 5, overflow: 'hidden' }}>
              <div
                style={{
                  width: `${pct}%`,
                  height: '100%',
                  background: 'linear-gradient(90deg, var(--color-primary), color-mix(in srgb, var(--color-primary) 60%, transparent))',
                  transition: 'width 200ms ease-out',
                }}
              />
            </div>
            <div
              style={{
                width: 56,
                flexShrink: 0,
                textAlign: 'right',
                fontFamily: 'var(--font-mono, monospace)',
                fontSize: '0.74rem',
                color: 'var(--color-text)',
              }}
            >
              {d.value}
            </div>
          </div>
        )
      })}
    </div>
  )
}

/* payload JSON 展示 */
function PayloadView({ raw }: { raw: string | null }) {
  const { t } = useTranslation('adminRuntimeLogs')
  const parsed = useMemo(() => parsePayloadJson(raw), [raw])
  let pretty: string
  if (parsed === null || parsed === undefined) {
    pretty = t('payload.empty')
  } else if (typeof parsed === 'string') {
    // 解析失败回退为原始字符串
    pretty = parsed
  } else {
    try {
      pretty = JSON.stringify(parsed, null, 2)
    } catch {
      pretty = String(parsed)
    }
  }
  return (
    <pre
      className="test-result-box"
      style={{ maxHeight: 360, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}
    >
      {pretty}
    </pre>
  )
}

/* ------------------------------------------------------------------ */
/*  总览 Tab                                                            */
/* ------------------------------------------------------------------ */

function StatsTab({ stats, isLoading }: { stats: ReturnType<typeof useStats>['stats']; isLoading: boolean }) {
  const { t } = useTranslation('adminRuntimeLogs')
  if (isLoading && !stats) return <Loading text={t('stats.loading')} />
  if (!stats) return <EmptyState title={t('empty.noStats')} icon="audit" />

  const categoryRows = Object.entries(stats.by_category || {})
    .map(([label, value]) => ({ label, value: Number(value) }))
    .sort((a, b) => b.value - a.value)
  const sourceRows = Object.entries(stats.by_source || {})
    .map(([label, value]) => ({ label, value: Number(value) }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 10)
  const levelEntries = Object.entries(stats.by_level || {})
  const levelTotal = levelEntries.reduce((s, [, v]) => s + Number(v), 0) || 1
  const successRate =
    typeof stats.success_rate === 'number'
      ? stats.success_rate <= 1
        ? stats.success_rate * 100
        : stats.success_rate
      : 0
  const recentErrors = stats.recent_errors ?? []

  return (
    <div>
      {/* 统计卡片 */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          gap: 12,
          marginBottom: 16,
        }}
      >
        <StatCard label={t('stats.totalLogs')} value={stats.total ?? 0} hint={t('stats.totalLogsHint')} />
        <StatCard label={t('stats.todayNew')} value={stats.today ?? 0} hint={t('stats.todayNewHint')} accent="#3b82f6" />
        <StatCard
          label={t('stats.successRate')}
          value={`${successRate.toFixed(1)}%`}
          hint={t('stats.successRateHint')}
          accent={successRate >= 95 ? '#22c55e' : successRate >= 80 ? '#eab308' : '#ef4444'}
        />
        <StatCard
          label={t('stats.recentErrors')}
          value={recentErrors.length}
          hint={t('stats.recentErrorsHint')}
          accent={recentErrors.length === 0 ? '#22c55e' : '#ef4444'}
        />
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
          gap: 16,
          marginBottom: 16,
        }}
      >
        {/* 分类分布 */}
        <div className="admin-card">
          <div className="admin-card-header">
            <span className="admin-card-title">{t('distributions.category')}</span>
          </div>
          <BarList data={categoryRows} />
        </div>

        {/* 等级分布 */}
        <div className="admin-card">
          <div className="admin-card-header">
            <span className="admin-card-title">{t('distributions.level')}</span>
          </div>
          {levelEntries.length === 0 ? (
            <EmptyState title={t('empty.noData')} size="sm" />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {levelEntries.map(([level, count]) => {
                const meta = levelMeta(level)
                const pct = ((Number(count) / levelTotal) * 100).toFixed(1)
                return (
                  <div key={level} style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: '0.8rem' }}>
                    <span
                      className="badge"
                      style={{ background: meta.bg, color: meta.color, width: 64, justifyContent: 'center' }}
                    >
                      {meta.label}
                    </span>
                    <div style={{ flex: 1, height: 10, background: 'var(--color-surface-raised)', borderRadius: 5, overflow: 'hidden' }}>
                      <div
                        style={{
                          width: `${Math.max(2, Number(pct))}%`,
                          height: '100%',
                          background: meta.color,
                          opacity: 0.85,
                        }}
                      />
                    </div>
                    <span style={{ width: 88, textAlign: 'right', fontFamily: 'var(--font-mono, monospace)', fontSize: '0.74rem' }}>
                      {count} ({pct}%)
                    </span>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>

      {/* 来源分布 */}
      <div className="admin-card" style={{ marginBottom: 16 }}>
        <div className="admin-card-header">
          <span className="admin-card-title">{t('distributions.sourceTop')}</span>
        </div>
        <BarList data={sourceRows} />
      </div>

      {/* 最近错误 */}
      <div className="admin-card">
        <div className="admin-card-header">
          <span className="admin-card-title">{t('distributions.recentErrors')}</span>
        </div>
        {recentErrors.length === 0 ? (
          <EmptyState title={t('empty.noErrors')} icon="check" />
        ) : (
          <div className="admin-table-wrapper">
            <table className="admin-table">
              <thead>
                <tr>
                  <th style={{ width: 160 }}>{t('table.time')}</th>
                  <th style={{ width: 80 }}>{t('table.level')}</th>
                  <th style={{ width: 110 }}>{t('table.category')}</th>
                  <th style={{ width: 130 }}>{t('table.source')}</th>
                  <th>{t('table.eventMessage')}</th>
                </tr>
              </thead>
              <tbody>
                {recentErrors.slice(0, 10).map((e) => {
                  const meta = levelMeta(e.level)
                  return (
                    <tr key={e.id}>
                      <td style={{ fontSize: '0.72rem', color: '#9aa' }}>{fmtTime(e.created_at)}</td>
                      <td>
                        <span className="badge" style={{ background: meta.bg, color: meta.color }}>
                          {meta.label}
                        </span>
                      </td>
                      <td className="admin-table-mono" style={{ fontSize: '0.74rem' }}>{e.category || '-'}</td>
                      <td className="admin-table-mono" style={{ fontSize: '0.74rem' }}>{e.source || '-'}</td>
                      <td>
                        <div style={{ fontWeight: 600 }}>{e.event || '-'}</div>
                        {e.message && (
                          <div style={{ fontSize: '0.72rem', color: '#9aa', marginTop: 2 }}>
                            {truncate(e.message, 160)}
                          </div>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  日志列表 Tab                                                        */
/* ------------------------------------------------------------------ */

function LogsTab({
  filters,
  setFilters,
  onExport,
  onBatchDelete,
  exporting,
  cleaning,
}: {
  filters: RuntimeLogListParams & { success: string; start_time: string; end_time: string }
  setFilters: (f: typeof filters) => void
  onExport: () => void
  onBatchDelete: () => void
  exporting: boolean
  cleaning: boolean
}) {
  const queryClient = useQueryClient()
  const { t } = useTranslation('adminRuntimeLogs')
  const [page, setPage] = useState(1)
  const [detailId, setDetailId] = useState<string | null>(null)
  const pageSize = 20

  // 仅在用户触发查询时刷新
  const [committed, setCommitted] = useState<RuntimeLogListParams & { success: string; start_time: string; end_time: string }>(filters)

  const queryParams: RuntimeLogListParams = useMemo(
    () => ({
      category: committed.category || undefined,
      source: committed.source || undefined,
      level: committed.level || undefined,
      success: committed.success === '' ? undefined : committed.success,
      session_id: committed.session_id || undefined,
      keyword: committed.keyword || undefined,
      start_time: committed.start_time ? new Date(committed.start_time).toISOString() : undefined,
      end_time: committed.end_time ? new Date(committed.end_time).toISOString() : undefined,
      page,
      page_size: pageSize,
    }),
    [committed, page],
  )

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ['runtime-logs', 'list', queryParams],
    queryFn: () => listRuntimeLogs(queryParams).then((r) => r.data.data),
  })

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteRuntimeLog(id),
    onSuccess: () => {
      toast.success(t('toast.deleted'))
      void queryClient.invalidateQueries({ queryKey: ['runtime-logs'] })
    },
    onError: (err: unknown) => toast.error(t('toast.deleteFailed'), getErrorMessage(err)),
  })

  const handleSearch = () => {
    setPage(1)
    setCommitted(filters)
  }

  const handleReset = () => {
    const empty = {
      category: '',
      source: '',
      level: '',
      success: '',
      session_id: '',
      keyword: '',
      start_time: '',
      end_time: '',
      page: 1,
      page_size: pageSize,
    } as typeof filters
    setFilters(empty)
    setCommitted(empty)
    setPage(1)
  }

  const handleDelete = async (item: RuntimeLogItem) => {
    const ok = await confirm({
      title: t('confirm.deleteTitle'),
      message: t('confirm.deleteMessage', { target: item.event || item.id }),
      variant: 'danger',
      confirmText: t('confirm.deleteConfirm'),
    })
    if (!ok) return
    deleteMut.mutate(item.id)
  }

  return (
    <div>
      {/* 筛选区 */}
      <div
        className="admin-toolbar"
        style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'flex-end' }}
      >
        <div className="admin-form-group" style={{ marginBottom: 0 }}>
          <label style={{ fontSize: '0.65rem', display: 'block', marginBottom: 2, color: 'var(--color-text-muted)' }}>{t('filters.category')}</label>
          <select
            className="admin-filter-select"
            value={filters.category}
            onChange={(e) => setFilters({ ...filters, category: e.target.value })}
          >
            {categoryOptions(t).map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>
        <div className="admin-form-group" style={{ marginBottom: 0 }}>
          <label style={{ fontSize: '0.65rem', display: 'block', marginBottom: 2, color: 'var(--color-text-muted)' }}>{t('filters.level')}</label>
          <select
            className="admin-filter-select"
            value={filters.level}
            onChange={(e) => setFilters({ ...filters, level: e.target.value })}
          >
            {levelOptions(t).map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>
        <div className="admin-form-group" style={{ marginBottom: 0 }}>
          <label style={{ fontSize: '0.65rem', display: 'block', marginBottom: 2, color: 'var(--color-text-muted)' }}>{t('filters.status')}</label>
          <select
            className="admin-filter-select"
            value={filters.success}
            onChange={(e) => setFilters({ ...filters, success: e.target.value })}
          >
            {statusOptions(t).map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>
        <div className="admin-form-group" style={{ marginBottom: 0, flex: 1, minWidth: 200 }}>
          <label style={{ fontSize: '0.65rem', display: 'block', marginBottom: 2, color: 'var(--color-text-muted)' }}>{t('filters.keyword')}</label>
          <input
            className="admin-search-input"
            style={{ width: '100%' }}
            value={filters.keyword}
            onChange={(e) => setFilters({ ...filters, keyword: e.target.value })}
            placeholder={t('filters.keywordPlaceholder')}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleSearch()
            }}
          />
        </div>
        <div className="admin-form-group" style={{ marginBottom: 0 }}>
          <label style={{ fontSize: '0.65rem', display: 'block', marginBottom: 2, color: 'var(--color-text-muted)' }}>{t('filters.startTime')}</label>
          <input
            type="datetime-local"
            className="admin-filter-select"
            value={filters.start_time}
            onChange={(e) => setFilters({ ...filters, start_time: e.target.value })}
          />
        </div>
        <div className="admin-form-group" style={{ marginBottom: 0 }}>
          <label style={{ fontSize: '0.65rem', display: 'block', marginBottom: 2, color: 'var(--color-text-muted)' }}>{t('filters.endTime')}</label>
          <input
            type="datetime-local"
            className="admin-filter-select"
            value={filters.end_time}
            onChange={(e) => setFilters({ ...filters, end_time: e.target.value })}
          />
        </div>
        <div className="admin-actions" style={{ marginBottom: 0 }}>
          <button className="btn btn-primary" onClick={handleSearch} disabled={isLoading}>
            <ICONS.search size={14} />
            {isLoading ? t('actions.searching') : t('actions.search')}
          </button>
          <button className="btn btn-secondary" onClick={handleReset} disabled={isLoading}>
            {t('actions.reset')}
          </button>
          <button className="btn btn-secondary" onClick={onExport} disabled={exporting} title={t('actions.exportTitle')}>
            <ICONS.download size={14} />
            {exporting ? t('actions.exporting') : t('actions.export')}
          </button>
          <button className="btn btn-danger" onClick={onBatchDelete} disabled={cleaning} title={t('actions.cleanTitle')}>
            <ICONS.empty size={14} />
            {cleaning ? t('actions.cleaning') : t('actions.batchClean')}
          </button>
        </div>
      </div>

      <div className="admin-table-wrapper" style={{ marginTop: 12 }}>
        <table className="admin-table">
          <thead>
            <tr>
              <th style={{ width: 160 }}>{t('table.time')}</th>
              <th style={{ width: 110 }}>{t('table.category')}</th>
              <th style={{ width: 80 }}>{t('table.level')}</th>
              <th style={{ width: 140 }}>{t('table.source')}</th>
              <th>{t('table.event')}</th>
              <th style={{ width: 100 }}>{t('table.duration')}</th>
              <th style={{ width: 90 }}>{t('table.status')}</th>
              <th style={{ width: 150 }}>{t('table.actions')}</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr>
                <td colSpan={8} style={{ textAlign: 'center', padding: 24, color: '#9aa' }}>
                  {isLoading || isFetching ? t('empty.loading') : t('empty.noLogs')}
                </td>
              </tr>
            ) : (
              items.map((it) => {
                const meta = levelMeta(it.level)
                return (
                  <tr key={it.id}>
                    <td style={{ fontSize: '0.72rem', color: '#9aa' }}>{fmtTime(it.created_at)}</td>
                    <td className="admin-table-mono" style={{ fontSize: '0.74rem' }}>{it.category || '-'}</td>
                    <td>
                      <span className="badge" style={{ background: meta.bg, color: meta.color }}>
                        {meta.label}
                      </span>
                    </td>
                    <td className="admin-table-mono" style={{ fontSize: '0.74rem' }} title={it.source}>
                      {truncate(it.source || '-', 24)}
                    </td>
                    <td title={it.message || ''}>
                      <div style={{ fontWeight: 600 }}>{truncate(it.event || '-', 60)}</div>
                      {it.message && (
                        <div style={{ fontSize: '0.72rem', color: '#9aa', marginTop: 2 }}>
                          {truncate(it.message, 80)}
                        </div>
                      )}
                    </td>
                    <td style={{ fontFamily: 'var(--font-mono, monospace)', fontSize: '0.74rem' }}>
                      {fmtDuration(it.duration_ms)}
                    </td>
                    <td>
                      {it.success ? (
                        <span className="badge success">{t('filters.status.success')}</span>
                      ) : (
                        <span className="badge failed">{t('filters.status.failed')}</span>
                      )}
                    </td>
                    <td>
                      <div className="admin-actions">
                        <button
                          className="admin-action-btn"
                          onClick={() => setDetailId(it.id)}
                        >
                          {t('actions.detail')}
                        </button>
                        <button
                          className="admin-action-btn"
                          onClick={() => void handleDelete(it)}
                          disabled={deleteMut.isPending && deleteMut.variables === it.id}
                        >
                          {deleteMut.isPending && deleteMut.variables === it.id ? t('actions.deleting') : t('actions.delete')}
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>

      {total > 0 && (
        <div className="admin-pagination">
          <span className="page-info">
            {t('pagination.info', { page, totalPages, total })}
          </span>
          <div className="page-buttons">
            <button
              className="page-btn"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
            >
              {t('pagination.prev')}
            </button>
            <button
              className="page-btn"
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
            >
              {t('pagination.next')}
            </button>
          </div>
        </div>
      )}

      {detailId && (
        <LogDetailModal
          id={detailId}
          onClose={() => setDetailId(null)}
        />
      )}
    </div>
  )
}

function LogDetailModal({ id, onClose }: { id: string; onClose: () => void }) {
  const { t } = useTranslation('adminRuntimeLogs')
  const { data, isLoading } = useQuery({
    queryKey: ['runtime-logs', 'detail', id],
    queryFn: () => getRuntimeLogDetail(id).then((r) => r.data.data),
  })

  return (
    <Modal
      title={t('detail.title', { id: id.slice(0, 8) })}
      onClose={onClose}
      footer={
        <button className="btn btn-secondary" onClick={onClose}>
          {t('actions.close')}
        </button>
      }
    >
      {isLoading ? (
        <Loading text={t('detail.loading')} />
      ) : !data ? (
        <EmptyState title={t('empty.noLogFound')} icon="audit" />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
              gap: 8,
              fontSize: '0.8rem',
            }}
          >
            <MetaItem label={t('detail.time')} value={fmtTime(data.created_at)} />
            <MetaItem label={t('detail.category')} value={data.category || '-'} mono />
            <MetaItem label={t('detail.source')} value={data.source || '-'} mono />
            <MetaItem label={t('detail.event')} value={data.event || '-'} />
            <MetaItem
              label={t('detail.level')}
              value={
                <span
                  className="badge"
                  style={{ background: levelMeta(data.level).bg, color: levelMeta(data.level).color }}
                >
                  {levelMeta(data.level).label}
                </span>
              }
            />
            <MetaItem
              label={t('detail.status')}
              value={data.success ? <span className="badge success">{t('filters.status.success')}</span> : <span className="badge failed">{t('filters.status.failed')}</span>}
            />
            <MetaItem label={t('detail.duration')} value={fmtDuration(data.duration_ms)} mono />
            <MetaItem label={t('detail.statusCode')} value={data.status_code != null ? String(data.status_code) : '-'} mono />
            <MetaItem label={t('detail.userId')} value={data.user_id || '-'} mono />
            <MetaItem label={t('detail.ip')} value={data.ip_address || '-'} mono />
            <MetaItem label={t('detail.sessionId')} value={data.session_id || '-'} mono />
            <MetaItem label={t('detail.tenant')} value={data.tenant_id || '-'} mono />
          </div>

          {data.message && (
            <div>
              <div style={{ fontSize: '0.7rem', color: 'var(--color-text-muted)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                {t('detail.message')}
              </div>
              <div className="test-result-box" style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                {data.message}
              </div>
            </div>
          )}

          <div>
            <div style={{ fontSize: '0.7rem', color: 'var(--color-text-muted)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              {t('detail.payload')}
            </div>
            <PayloadView raw={data.payload_json} />
          </div>
        </div>
      )}
    </Modal>
  )
}

function MetaItem({ label, value, mono }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div>
      <div style={{ fontSize: '0.65rem', color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
        {label}
      </div>
      <div style={mono ? { fontFamily: 'var(--font-mono, monospace)', fontSize: '0.78rem' } : undefined}>
        {value}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  问答交互 Tab                                                        */
/* ------------------------------------------------------------------ */

function ConversationsTab() {
  const { t } = useTranslation('adminRuntimeLogs')
  const { data, isLoading } = useQuery({
    queryKey: ['runtime-logs', 'conversations'],
    queryFn: () => getConversationsSummary().then((r) => r.data.data),
  })

  if (isLoading && !data) return <Loading text={t('conversations.loading')} />
  if (!data) return <EmptyState title={t('empty.noConversations')} icon="agent" />

  const recent = data.recent ?? []

  return (
    <div>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          gap: 12,
          marginBottom: 16,
        }}
      >
        <StatCard label={t('conversations.totalConversations')} value={data.total_conversations ?? 0} hint={t('conversations.totalConversationsHint')} />
        <StatCard label={t('conversations.totalMessages')} value={data.total_messages ?? 0} hint={t('conversations.totalMessagesHint')} accent="#3b82f6" />
        <StatCard label={t('conversations.userMessages')} value={data.user_messages ?? 0} hint={t('conversations.userMessagesHint')} accent="#22c55e" />
        <StatCard label={t('conversations.assistantMessages')} value={data.assistant_messages ?? 0} hint={t('conversations.assistantMessagesHint')} accent="#a855f7" />
      </div>

      <div className="admin-card">
        <div className="admin-card-header">
          <span className="admin-card-title">{t('conversations.recentMessages', { count: recent.length })}</span>
        </div>
        {recent.length === 0 ? (
          <EmptyState title={t('empty.noMessages')} icon="agent" />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {recent.slice(0, 20).map((m) => {
              const isUser = String(m.role || '').toLowerCase() === 'user'
              return (
                <div
                  key={m.id}
                  style={{
                    display: 'flex',
                    gap: 12,
                    padding: 12,
                    borderRadius: 8,
                    background: 'var(--color-surface-raised)',
                    border: '1px solid var(--color-border, #3a3f4b)',
                  }}
                >
                  <span
                    className="badge"
                    style={{
                      background: isUser ? 'rgba(34,197,94,.15)' : 'rgba(168,85,247,.15)',
                      color: isUser ? '#22c55e' : '#a855f7',
                      alignSelf: 'flex-start',
                      flexShrink: 0,
                      textTransform: 'capitalize',
                    }}
                  >
                    {m.role || t('conversations.unknownRole')}
                  </span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: '0.84rem', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                      {truncate(m.content || '', 200)}
                    </div>
                    <div style={{ fontSize: '0.7rem', color: 'var(--color-text-muted)', marginTop: 4 }}>
                      {fmtTime(m.created_at)}
                      <span style={{ margin: '0 6px' }}>·</span>
                      <span style={{ fontFamily: 'var(--font-mono, monospace)' }}>
                        {(m.conversation_id || '').slice(0, 8)}
                      </span>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  模块状态 Tab                                                        */
/* ------------------------------------------------------------------ */

function ModulesTab() {
  const { t } = useTranslation('adminRuntimeLogs')
  const { data, isLoading } = useQuery({
    queryKey: ['runtime-logs', 'modules'],
    queryFn: () => getModuleStatus().then((r) => r.data.data),
  })

  if (isLoading && !data) return <Loading text={t('modules.loading')} />
  if (!data || !data.modules) return <EmptyState title={t('empty.noModules')} icon="audit" />

  return (
    <div>
      <div style={{ marginBottom: 12, fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>
        {t('modules.checkedAt', { time: fmtTime(data.checked_at) })}
      </div>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
          gap: 12,
        }}
      >
        {data.modules.map((m) => {
          const total = m.total ?? 0
          const active = m.active ?? 0
          const inactive = m.inactive ?? 0
          const rate = total > 0 ? (active / total) * 100 : 0
          return (
            <div key={m.key} className="admin-card" style={{ marginBottom: 0 }}>
              <div className="admin-card-header" style={{ marginBottom: 8 }}>
                <span className="admin-card-title">{m.label || m.key}</span>
              </div>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(3, 1fr)',
                  gap: 8,
                  marginBottom: 10,
                }}
              >
                <ModuleStat label={t('modules.total')} value={total} color="#3b82f6" />
                <ModuleStat label={t('modules.active')} value={active} color="#22c55e" />
                <ModuleStat label={t('modules.inactive')} value={inactive} color="#ef4444" />
              </div>
              <div>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    fontSize: '0.72rem',
                    color: 'var(--color-text-muted)',
                    marginBottom: 4,
                  }}
                >
                  <span>{t('modules.activeRate')}</span>
                  <span style={{ fontFamily: 'var(--font-mono, monospace)' }}>
                    {rate.toFixed(1)}%
                  </span>
                </div>
                <div
                  style={{
                    height: 8,
                    background: 'var(--color-surface-raised)',
                    borderRadius: 4,
                    overflow: 'hidden',
                  }}
                >
                  <div
                    style={{
                      width: `${Math.max(0, Math.min(100, rate))}%`,
                      height: '100%',
                      background:
                        rate >= 80
                          ? 'linear-gradient(90deg, #22c55e, #4ade80)'
                          : rate >= 50
                            ? 'linear-gradient(90deg, #eab308, #facc15)'
                            : 'linear-gradient(90deg, #ef4444, #f87171)',
                      transition: 'width 200ms ease-out',
                    }}
                  />
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function ModuleStat({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div
      style={{
        textAlign: 'center',
        padding: '8px 4px',
        borderRadius: 6,
        background: 'var(--color-surface-raised)',
      }}
    >
      <div
        style={{
          fontSize: 'var(--text-lg)',
          fontWeight: 700,
          color,
          fontFamily: 'var(--font-display)',
        }}
      >
        {value}
      </div>
      <div style={{ fontSize: '0.68rem', color: 'var(--color-text-muted)', marginTop: 2 }}>
        {label}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  useStats hook                                                       */
/* ------------------------------------------------------------------ */

function useStats() {
  const queryClient = useQueryClient()
  const { data: stats, isLoading } = useQuery({
    queryKey: ['runtime-logs', 'stats'],
    queryFn: () => getRuntimeStats().then((r) => r.data.data),
  })

  return {
    stats,
    isLoading,
    refresh: () => queryClient.invalidateQueries({ queryKey: ['runtime-logs'] }),
  }
}

/* ------------------------------------------------------------------ */
/*  页面                                                                */
/* ------------------------------------------------------------------ */

export default function RuntimeLogsPage() {
  const { t } = useTranslation('adminRuntimeLogs')
  const [tab, setTab] = useState<Tab>('stats')
  const queryClient = useQueryClient()
  const { stats, isLoading: statsLoading, refresh } = useStats()

  const [filters, setFilters] = useState<
    RuntimeLogListParams & { success: string; start_time: string; end_time: string }
  >({
    category: '',
    source: '',
    level: '',
    success: '',
    session_id: '',
    keyword: '',
    start_time: '',
    end_time: '',
    page: 1,
    page_size: 20,
  })

  // 批量清理弹窗 — 由 confirm() 触发；提供表单输入
  const [cleanOpen, setCleanOpen] = useState(false)
  const [cleanCategory, setCleanCategory] = useState('')
  const [cleanBeforeDays, setCleanBeforeDays] = useState(7)

  const exportMut = useMutation({
    mutationFn: () => {
      const params: RuntimeLogListParams = {
        category: filters.category || undefined,
        source: filters.source || undefined,
        level: filters.level || undefined,
        success: filters.success === '' ? undefined : filters.success,
        session_id: filters.session_id || undefined,
        keyword: filters.keyword || undefined,
        start_time: filters.start_time ? new Date(filters.start_time).toISOString() : undefined,
        end_time: filters.end_time ? new Date(filters.end_time).toISOString() : undefined,
      }
      return exportRuntimeLogs(params).then((r) => r.data.data)
    },
    onSuccess: (data) => {
      try {
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `runtime-logs-${new Date().toISOString().replace(/[:.]/g, '-')}.json`
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
        URL.revokeObjectURL(url)
        toast.success(t('toast.exportSuccess'), t('toast.exportSuccessDesc', { count: data.count }))
      } catch {
        toast.success(t('toast.exportSuccess'), t('toast.exportSuccessDesc', { count: data.count }))
      }
    },
    onError: (err: unknown) => toast.error(t('toast.exportFailed'), getErrorMessage(err)),
  })

  const cleanMut = useMutation({
    mutationFn: () =>
      batchDeleteRuntimeLogs({
        category: cleanCategory || undefined,
        before_days: cleanBeforeDays > 0 ? cleanBeforeDays : undefined,
      }).then((r) => r.data.data),
    onSuccess: (data) => {
      toast.success(t('toast.cleanSuccess'), t('toast.cleanSuccessDesc', { count: data?.deleted_count ?? 0 }))
      setCleanOpen(false)
      void refresh()
    },
    onError: (err: unknown) => toast.error(t('toast.cleanFailed'), getErrorMessage(err)),
  })

  const handleRefresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ['runtime-logs'] })
    toast.success(t('toast.refreshed'))
  }

  const handleBatchDelete = () => {
    setCleanCategory(filters.category || '')
    setCleanBeforeDays(7)
    setCleanOpen(true)
  }

  const confirmBatchDelete = async () => {
    const ok = await confirm({
      title: t('confirm.batchCleanTitle'),
      message: (
        <div style={{ fontSize: '0.85rem' }}>
          <Trans
            i18nKey={cleanCategory ? 'confirm.batchCleanMessageCategory' : 'confirm.batchCleanMessageAll'}
            ns="adminRuntimeLogs"
            components={{ strong: <strong /> }}
            values={{ category: cleanCategory, days: cleanBeforeDays }}
          />
        </div>
      ),
      variant: 'danger',
      confirmText: t('confirm.batchCleanConfirm'),
    })
    if (!ok) return
    cleanMut.mutate()
  }

  return (
    <div>
      {/* Header */}
      <div
        className="admin-page-header"
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          gap: 12,
          flexWrap: 'wrap',
        }}
      >
        <div>
          <h1 className="admin-page-title">{t('title')}</h1>
          <p className="admin-page-desc">
            {t('description')}
          </p>
        </div>
        <div className="admin-actions">
          <button
            className="btn btn-secondary"
            onClick={() => void handleRefresh()}
            title={t('actions.refreshTitle')}
          >
            <ICONS.refresh size={14} />
            {t('actions.refresh')}
          </button>
          <button
            className="btn btn-secondary"
            onClick={() => exportMut.mutate()}
            disabled={exportMut.isPending}
            title={t('actions.exportTitle')}
          >
            <ICONS.download size={14} />
            {exportMut.isPending ? t('actions.exporting') : t('actions.export')}
          </button>
          <button
            className="btn btn-danger"
            onClick={handleBatchDelete}
            disabled={cleanMut.isPending}
          >
            <ICONS.empty size={14} />
            {t('actions.batchClean')}
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="tabs">
        <button
          className={`tab-item${tab === 'stats' ? ' active' : ''}`}
          onClick={() => setTab('stats')}
        >
          {t('tabs.stats')}
        </button>
        <button
          className={`tab-item${tab === 'logs' ? ' active' : ''}`}
          onClick={() => setTab('logs')}
        >
          {t('tabs.logs')}
        </button>
        <button
          className={`tab-item${tab === 'conversations' ? ' active' : ''}`}
          onClick={() => setTab('conversations')}
        >
          {t('tabs.conversations')}
        </button>
        <button
          className={`tab-item${tab === 'modules' ? ' active' : ''}`}
          onClick={() => setTab('modules')}
        >
          {t('tabs.modules')}
        </button>
      </div>

      {tab === 'stats' && <StatsTab stats={stats} isLoading={statsLoading} />}
      {tab === 'logs' && (
        <LogsTab
          filters={filters}
          setFilters={setFilters}
          onExport={() => exportMut.mutate()}
          onBatchDelete={handleBatchDelete}
          exporting={exportMut.isPending}
          cleaning={cleanMut.isPending}
        />
      )}
      {tab === 'conversations' && <ConversationsTab />}
      {tab === 'modules' && <ModulesTab />}

      {/* 批量清理配置弹窗 */}
      {cleanOpen && (
        <Modal
          title={t('cleanModal.title')}
          onClose={() => setCleanOpen(false)}
          footer={
            <>
              <button
                className="btn btn-danger"
                onClick={() => void confirmBatchDelete()}
                disabled={cleanMut.isPending}
              >
                {cleanMut.isPending ? t('actions.cleaning') : t('actions.executeClean')}
              </button>
              <button
                className="btn btn-secondary"
                onClick={() => setCleanOpen(false)}
                disabled={cleanMut.isPending}
              >
                {t('actions.cancel')}
              </button>
            </>
          }
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div className="admin-form-row">
              <label className="admin-form-label">{t('cleanModal.categoryLabel')}</label>
              <select
                className="admin-form-select"
                value={cleanCategory}
                onChange={(e) => setCleanCategory(e.target.value)}
              >
                {categoryOptions(t).map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
            <div className="admin-form-row">
              <label className="admin-form-label">{t('cleanModal.daysLabel')}</label>
              <input
                type="number"
                className="admin-form-input"
                min={1}
                value={cleanBeforeDays}
                onChange={(e) => setCleanBeforeDays(Math.max(1, Number(e.target.value) || 7))}
              />
              <span className="admin-form-hint" style={{ marginTop: 4, display: 'block' }}>
                {t('cleanModal.daysHint', { days: cleanBeforeDays })}
              </span>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}
