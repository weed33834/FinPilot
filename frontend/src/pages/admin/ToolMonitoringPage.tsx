import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import i18n from '../../i18n/config.ts'
import zhCnResource from '../../i18n/locales/zh-CN/admin-tool-monitoring.json'
import enResource from '../../i18n/locales/en/admin-tool-monitoring.json'
import EmptyState from '../../components/ui/EmptyState.tsx'
import Loading from '../../components/ui/Loading.tsx'
import { ICONS } from '../../components/ui/Icons.tsx'
import {
  getAuditTrail,
  getCircuitBreakers,
  getToolHealth,
  resetCircuitBreaker,
  triggerHealthCheck,
  type CircuitBreakerState,
  type ToolAuditRecord,
  type ToolHealthStat,
} from '../../api/toolMonitoring.ts'

// 命名空间未在 i18n/config.ts 中注册（按要求不修改该文件），这里在模块加载时
// 同步注入资源，子组件通过 useTranslation('adminToolMonitoring') 消费。
const NS = 'adminToolMonitoring'
if (!i18n.hasResourceBundle('zh-CN', NS)) {
  i18n.addResourceBundle('zh-CN', NS, zhCnResource)
}
if (!i18n.hasResourceBundle('en', NS)) {
  i18n.addResourceBundle('en', NS, enResource)
}

type Tab = 'health' | 'breakers' | 'audit'

function truncate(v: unknown, max = 80): string {
  let s: string
  if (v == null) s = '-'
  else if (typeof v === 'string') s = v
  else {
    try {
      s = JSON.stringify(v)
    } catch {
      s = String(v)
    }
  }
  return s.length > max ? s.slice(0, max) + '…' : s
}

/* ------------------------------------------------------------------ */
/*  工具健康                                                            */
/* ------------------------------------------------------------------ */

function HealthTab() {
  const { t } = useTranslation(NS)
  const [stats, setStats] = useState<Record<string, ToolHealthStat>>({})
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [checking, setChecking] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await getToolHealth()
      setStats(res.data.data ?? {})
    } catch (e) {
      setError(e instanceof Error ? e.message : t('health.loadFailed'))
    } finally {
      setLoading(false)
    }
  }, [t])

  useEffect(() => {
    void load()
  }, [load])

  const handleCheck = async (name: string) => {
    setChecking(name)
    setError(null)
    try {
      await triggerHealthCheck(name)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : t('health.checkFailed'))
    } finally {
      setChecking(null)
    }
  }

  const rows = Object.entries(stats)

  return (
    <div>
      <div className="admin-toolbar-right" style={{ marginBottom: 14 }}>
        <button className="btn btn-secondary" onClick={() => void load()} disabled={loading}>
          <ICONS.refresh size={14} />
          {t('actions.refresh')}
        </button>
      </div>
      {error && (
        <div
          className="admin-error"
          style={{
            marginBottom: 12,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 12,
          }}
        >
          <span>{error}</span>
          <button className="admin-action-btn" onClick={() => void load()} disabled={loading}>
            {t('actions.retry')}
          </button>
        </div>
      )}
      {loading && rows.length === 0 ? (
        <Loading text={t('loading')} />
      ) : rows.length === 0 ? (
        error ? null : (
          <EmptyState title={t('health.empty')} description={t('health.emptyDesc')} />
        )
      ) : (
        <div className="admin-table-wrapper">
          <table className="admin-table">
            <thead>
              <tr>
                <th>{t('health.columns.tool')}</th>
                <th style={{ width: 110 }}>{t('health.columns.status')}</th>
                <th style={{ width: 110 }}>{t('health.columns.successRate')}</th>
                <th style={{ width: 120 }}>{t('health.columns.avgLatency')}</th>
                <th style={{ width: 100 }}>{t('health.columns.totalCalls')}</th>
                <th style={{ width: 170 }}>{t('health.columns.lastCheck')}</th>
                <th style={{ width: 110 }}>{t('health.columns.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(([name, s]) => {
                const healthy = s.healthy ?? s.status === 'healthy'
                const rate =
                  typeof s.success_rate === 'number'
                    ? s.success_rate * (s.success_rate <= 1 ? 100 : 1)
                    : s.total_calls
                      ? ((s.success_count ?? 0) / s.total_calls) * 100
                      : null
                return (
                  <tr key={name}>
                    <td className="admin-table-mono">{name}</td>
                    <td>
                      <span
                        className="badge"
                        style={{
                          background: healthy ? 'rgba(34,197,94,.15)' : 'rgba(239,68,68,.15)',
                          color: healthy ? '#22c55e' : '#ef4444',
                        }}
                      >
                        {healthy ? t('health.healthy') : t('health.unhealthy')}
                      </span>
                    </td>
                    <td>{rate != null ? `${rate.toFixed(1)}%` : '-'}</td>
                    <td>{s.avg_latency_ms != null ? `${Math.round(s.avg_latency_ms)} ms` : '-'}</td>
                    <td>{s.total_calls ?? '-'}</td>
                    <td style={{ fontSize: '0.72rem', color: '#9aa' }}>
                      {s.last_check_time ? new Date(String(s.last_check_time)).toLocaleString() : '-'}
                    </td>
                    <td>
                      <button
                        className="admin-action-btn"
                        onClick={() => void handleCheck(name)}
                        disabled={checking === name}
                      >
                        {checking === name ? t('actions.checking') : t('actions.check')}
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  断路器状态                                                          */
/* ------------------------------------------------------------------ */

const CB_STATE_META: Record<string, { color: string; bg: string }> = {
  CLOSED: { color: '#22c55e', bg: 'rgba(34,197,94,.15)' },
  OPEN: { color: '#ef4444', bg: 'rgba(239,68,68,.15)' },
  HALF_OPEN: { color: '#eab308', bg: 'rgba(234,179,8,.15)' },
}

function BreakersTab() {
  const { t } = useTranslation(NS)
  const [breakers, setBreakers] = useState<Record<string, CircuitBreakerState>>({})
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [resetting, setResetting] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await getCircuitBreakers()
      setBreakers(res.data.data ?? {})
    } catch (e) {
      setError(e instanceof Error ? e.message : t('breakers.loadFailed'))
    } finally {
      setLoading(false)
    }
  }, [t])

  useEffect(() => {
    void load()
  }, [load])

  const handleReset = async (name: string) => {
    if (!window.confirm(t('breakers.confirmReset', { name }))) return
    setResetting(name)
    try {
      await resetCircuitBreaker(name)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : t('breakers.resetFailed'))
    } finally {
      setResetting(null)
    }
  }

  const rows = Object.entries(breakers)

  return (
    <div>
      <div className="admin-toolbar-right" style={{ marginBottom: 14 }}>
        <button className="btn btn-secondary" onClick={() => void load()} disabled={loading}>
          <ICONS.refresh size={14} />
          {t('actions.refresh')}
        </button>
      </div>
      {error && (
        <div
          className="admin-error"
          style={{
            marginBottom: 12,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 12,
          }}
        >
          <span>{error}</span>
          <button className="admin-action-btn" onClick={() => void load()} disabled={loading}>
            {t('actions.retry')}
          </button>
        </div>
      )}
      {loading && rows.length === 0 ? (
        <Loading text={t('loading')} />
      ) : rows.length === 0 ? (
        error ? null : (
          <EmptyState title={t('breakers.empty')} description={t('breakers.emptyDesc')} />
        )
      ) : (
        <div className="admin-table-wrapper">
          <table className="admin-table">
            <thead>
              <tr>
                <th>{t('breakers.columns.tool')}</th>
                <th style={{ width: 130 }}>{t('breakers.columns.status')}</th>
                <th style={{ width: 100 }}>{t('breakers.columns.failureCount')}</th>
                <th style={{ width: 100 }}>{t('breakers.columns.successCount')}</th>
                <th style={{ width: 170 }}>{t('breakers.columns.lastFailure')}</th>
                <th style={{ width: 110 }}>{t('breakers.columns.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(([name, b]) => {
                const stateKey = String(b.state ?? '').toUpperCase()
                const meta = CB_STATE_META[stateKey]
                const label = meta
                  ? t(`breakers.states.${stateKey}`)
                  : b.state || '-'
                const color = meta?.color ?? '#9aa'
                const bg = meta?.bg ?? 'rgba(127,127,127,.15)'
                return (
                  <tr key={name}>
                    <td className="admin-table-mono">{name}</td>
                    <td>
                      <span className="badge" style={{ background: bg, color }}>
                        {label}
                      </span>
                    </td>
                    <td>{b.failure_count ?? 0}</td>
                    <td>{b.success_count ?? 0}</td>
                    <td style={{ fontSize: '0.72rem', color: '#9aa' }}>
                      {b.last_failure_time
                        ? new Date(String(b.last_failure_time)).toLocaleString()
                        : '-'}
                    </td>
                    <td>
                      <button
                        className="admin-action-btn"
                        onClick={() => void handleReset(name)}
                        disabled={resetting === name}
                      >
                        {resetting === name ? t('actions.resetting') : t('actions.reset')}
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  执行审计                                                            */
/* ------------------------------------------------------------------ */

function AuditTab() {
  const { t } = useTranslation(NS)
  const [records, setRecords] = useState<ToolAuditRecord[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [toolName, setToolName] = useState('')
  const [startTime, setStartTime] = useState('')
  const [endTime, setEndTime] = useState('')
  const [page, setPage] = useState(1)
  const pageSize = 10

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await getAuditTrail({
        tool_name: toolName.trim() || undefined,
        start_time: startTime ? new Date(startTime).toISOString() : undefined,
        end_time: endTime ? new Date(endTime).toISOString() : undefined,
        limit: 500,
      })
      setRecords(res.data.data ?? [])
      setPage(1)
    } catch (e) {
      setError(e instanceof Error ? e.message : t('audit.loadFailed'))
    } finally {
      setLoading(false)
    }
  }, [toolName, startTime, endTime, t])

  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const totalPages = Math.max(1, Math.ceil(records.length / pageSize))
  const pageRecords = records.slice((page - 1) * pageSize, page * pageSize)

  return (
    <div>
      <div
        className="admin-toolbar-left"
        style={{ marginBottom: 14, justifyContent: 'space-between' }}
      >
        <div className="admin-toolbar-left">
          <input
            className="admin-search-input"
            value={toolName}
            onChange={(e) => setToolName(e.target.value)}
            placeholder={t('audit.toolNamePlaceholder')}
            style={{ minWidth: 160 }}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void load()
            }}
          />
          <input
            type="datetime-local"
            className="admin-filter-select"
            value={startTime}
            onChange={(e) => setStartTime(e.target.value)}
            title={t('audit.startTimeTitle')}
          />
          <input
            type="datetime-local"
            className="admin-filter-select"
            value={endTime}
            onChange={(e) => setEndTime(e.target.value)}
            title={t('audit.endTimeTitle')}
          />
        </div>
        <button className="btn btn-primary" onClick={() => void load()} disabled={loading}>
          <ICONS.search size={14} />
          {loading ? t('actions.searching') : t('actions.search')}
        </button>
      </div>

      {error && (
        <div
          className="admin-error"
          style={{
            marginBottom: 12,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 12,
          }}
        >
          <span>{error}</span>
          <button className="admin-action-btn" onClick={() => void load()} disabled={loading}>
            {t('actions.retry')}
          </button>
        </div>
      )}

      {loading && records.length === 0 ? (
        <Loading text={t('loading')} />
      ) : records.length === 0 ? (
        error ? null : (
          <EmptyState title={t('audit.empty')} description={t('audit.emptyDesc')} />
        )
      ) : (
        <>
          <div className="admin-table-wrapper">
            <table className="admin-table">
              <thead>
                <tr>
                  <th style={{ width: 140 }}>{t('audit.columns.tool')}</th>
                  <th>{t('audit.columns.params')}</th>
                  <th>{t('audit.columns.result')}</th>
                  <th style={{ width: 80 }}>{t('audit.columns.status')}</th>
                  <th style={{ width: 100 }}>{t('audit.columns.latency')}</th>
                  <th style={{ width: 160 }}>{t('audit.columns.time')}</th>
                </tr>
              </thead>
              <tbody>
                {pageRecords.map((r, idx) => (
                  <tr key={r.id ?? idx}>
                    <td className="admin-table-mono" style={{ fontSize: '0.74rem' }}>
                      {r.tool_name ?? '-'}
                    </td>
                    <td
                      style={{ maxWidth: 240, fontFamily: 'var(--font-mono, monospace)', fontSize: '0.72rem' }}
                      title={truncate(r.params, 500)}
                    >
                      {truncate(r.params)}
                    </td>
                    <td
                      style={{ maxWidth: 240, fontFamily: 'var(--font-mono, monospace)', fontSize: '0.72rem' }}
                      title={truncate(r.result, 500)}
                    >
                      {truncate(r.result)}
                    </td>
                    <td>
                      {r.success ? (
                        <span className="badge success">{t('audit.success')}</span>
                      ) : (
                        <span className="badge failed">{t('audit.failed')}</span>
                      )}
                    </td>
                    <td>{r.latency_ms != null ? `${Math.round(r.latency_ms)} ms` : '-'}</td>
                    <td style={{ fontSize: '0.72rem', color: '#9aa' }}>
                      {(r.created_at || r.timestamp)
                        ? new Date(String(r.created_at || r.timestamp)).toLocaleString()
                        : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {records.length > pageSize && (
            <div className="admin-pagination">
              <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}>
                {t('audit.pagination.prev')}
              </button>
              <span>
                {t('audit.pagination.info', {
                  page,
                  totalPages,
                  total: records.length,
                })}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
              >
                {t('audit.pagination.next')}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  页面                                                                */
/* ------------------------------------------------------------------ */

export default function ToolMonitoringPage() {
  const { t } = useTranslation(NS)
  const [tab, setTab] = useState<Tab>('health')
  return (
    <div>
      <div className="admin-page-header">
        <h1 className="admin-page-title">{t('title')}</h1>
        <p className="admin-page-desc">{t('description')}</p>
      </div>

      <div className="tabs">
        <button
          className={`tab-item${tab === 'health' ? ' active' : ''}`}
          onClick={() => setTab('health')}
        >
          {t('tabs.health')}
        </button>
        <button
          className={`tab-item${tab === 'breakers' ? ' active' : ''}`}
          onClick={() => setTab('breakers')}
        >
          {t('tabs.breakers')}
        </button>
        <button
          className={`tab-item${tab === 'audit' ? ' active' : ''}`}
          onClick={() => setTab('audit')}
        >
          {t('tabs.audit')}
        </button>
      </div>

      {tab === 'health' && <HealthTab />}
      {tab === 'breakers' && <BreakersTab />}
      {tab === 'audit' && <AuditTab />}
    </div>
  )
}
