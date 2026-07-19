import { useCallback, useEffect, useState } from 'react'
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
import { ICONS } from '../../components/ui/Icons.tsx'

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
      setError(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

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
      setError(e instanceof Error ? e.message : '检查失败')
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
          刷新
        </button>
      </div>
      {error && <div className="admin-error" style={{ marginBottom: 12 }}>{error}</div>}
      <div className="admin-table-wrapper">
        <table className="admin-table">
          <thead>
            <tr>
              <th>工具</th>
              <th style={{ width: 110 }}>状态</th>
              <th style={{ width: 110 }}>成功率</th>
              <th style={{ width: 120 }}>平均延迟</th>
              <th style={{ width: 100 }}>调用数</th>
              <th style={{ width: 170 }}>最近检查</th>
              <th style={{ width: 110 }}>操作</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={7} style={{ textAlign: 'center', padding: 24, color: '#9aa' }}>
                  {loading ? '加载中…' : '暂无工具健康数据'}
                </td>
              </tr>
            ) : (
              rows.map(([name, s]) => {
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
                        {healthy ? '健康' : '异常'}
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
                        {checking === name ? '检查中…' : '立即检查'}
                      </button>
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  断路器状态                                                          */
/* ------------------------------------------------------------------ */

const CB_STATE_META: Record<string, { label: string; color: string; bg: string }> = {
  CLOSED: { label: 'CLOSED', color: '#22c55e', bg: 'rgba(34,197,94,.15)' },
  OPEN: { label: 'OPEN', color: '#ef4444', bg: 'rgba(239,68,68,.15)' },
  HALF_OPEN: { label: 'HALF_OPEN', color: '#eab308', bg: 'rgba(234,179,8,.15)' },
}

function BreakersTab() {
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
      setError(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const handleReset = async (name: string) => {
    if (!window.confirm(`确认重置工具 ${name} 的断路器？`)) return
    setResetting(name)
    try {
      await resetCircuitBreaker(name)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : '重置失败')
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
          刷新
        </button>
      </div>
      {error && <div className="admin-error" style={{ marginBottom: 12 }}>{error}</div>}
      <div className="admin-table-wrapper">
        <table className="admin-table">
          <thead>
            <tr>
              <th>工具</th>
              <th style={{ width: 130 }}>状态</th>
              <th style={{ width: 100 }}>失败次数</th>
              <th style={{ width: 100 }}>成功次数</th>
              <th style={{ width: 170 }}>最近失败</th>
              <th style={{ width: 110 }}>操作</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={6} style={{ textAlign: 'center', padding: 24, color: '#9aa' }}>
                  {loading ? '加载中…' : '暂无断路器记录'}
                </td>
              </tr>
            ) : (
              rows.map(([name, b]) => {
                const meta = CB_STATE_META[String(b.state ?? '').toUpperCase()] || {
                  label: b.state || '-',
                  color: '#9aa',
                  bg: 'rgba(127,127,127,.15)',
                }
                return (
                  <tr key={name}>
                    <td className="admin-table-mono">{name}</td>
                    <td>
                      <span
                        className="badge"
                        style={{ background: meta.bg, color: meta.color }}
                      >
                        {meta.label}
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
                        {resetting === name ? '重置中…' : '重置'}
                      </button>
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  执行审计                                                            */
/* ------------------------------------------------------------------ */

function AuditTab() {
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
      setError(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [toolName, startTime, endTime])

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
            placeholder="工具名筛选"
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
            title="起始时间"
          />
          <input
            type="datetime-local"
            className="admin-filter-select"
            value={endTime}
            onChange={(e) => setEndTime(e.target.value)}
            title="结束时间"
          />
        </div>
        <button className="btn btn-primary" onClick={() => void load()} disabled={loading}>
          <ICONS.search size={14} />
          {loading ? '查询中…' : '查询'}
        </button>
      </div>

      {error && <div className="admin-error" style={{ marginBottom: 12 }}>{error}</div>}

      <div className="admin-table-wrapper">
        <table className="admin-table">
          <thead>
            <tr>
              <th style={{ width: 140 }}>工具</th>
              <th>参数</th>
              <th>结果</th>
              <th style={{ width: 80 }}>状态</th>
              <th style={{ width: 100 }}>延迟</th>
              <th style={{ width: 160 }}>时间</th>
            </tr>
          </thead>
          <tbody>
            {pageRecords.length === 0 ? (
              <tr>
                <td colSpan={6} style={{ textAlign: 'center', padding: 24, color: '#9aa' }}>
                  {loading ? '加载中…' : '暂无审计记录'}
                </td>
              </tr>
            ) : (
              pageRecords.map((r, idx) => (
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
                      <span className="badge success">成功</span>
                    ) : (
                      <span className="badge failed">失败</span>
                    )}
                  </td>
                  <td>{r.latency_ms != null ? `${Math.round(r.latency_ms)} ms` : '-'}</td>
                  <td style={{ fontSize: '0.72rem', color: '#9aa' }}>
                    {(r.created_at || r.timestamp)
                      ? new Date(String(r.created_at || r.timestamp)).toLocaleString()
                      : '-'}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {records.length > pageSize && (
        <div className="admin-pagination">
          <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}>
            上一页
          </button>
          <span>
            第 {page} / {totalPages} 页（共 {records.length} 条）
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
          >
            下一页
          </button>
        </div>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  页面                                                                */
/* ------------------------------------------------------------------ */

export default function ToolMonitoringPage() {
  const [tab, setTab] = useState<Tab>('health')
  return (
    <div>
      <div className="admin-page-header">
        <h1 className="admin-page-title">工具监控</h1>
        <p className="admin-page-desc">工具健康 / 断路器状态 / 执行审计</p>
      </div>

      <div className="tabs">
        <button
          className={`tab-item${tab === 'health' ? ' active' : ''}`}
          onClick={() => setTab('health')}
        >
          工具健康
        </button>
        <button
          className={`tab-item${tab === 'breakers' ? ' active' : ''}`}
          onClick={() => setTab('breakers')}
        >
          断路器状态
        </button>
        <button
          className={`tab-item${tab === 'audit' ? ' active' : ''}`}
          onClick={() => setTab('audit')}
        >
          执行审计
        </button>
      </div>

      {tab === 'health' && <HealthTab />}
      {tab === 'breakers' && <BreakersTab />}
      {tab === 'audit' && <AuditTab />}
    </div>
  )
}
