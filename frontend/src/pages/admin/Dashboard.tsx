import { useEffect, useState } from 'react'
import { adminApi } from '../../api/adminClient.ts'
import Loading from '../../components/ui/Loading.tsx'
import { ICONS } from '../../components/ui/Icons.tsx'
import { getErrorMessage } from '../../utils/errors.ts'
import { formatDateTime } from '../../utils/format.ts'
import { getHealthCheck } from '../../api/settings.ts'

interface DashboardStats {
  models: { total: number; active: number; default: string }
  prompts: { total: number; active: number }
  tools: { total: number; active: number; builtin: number; custom: number }
  skills: { total: number; active: number }
  agents: { total: number; active: number }
  search_engines: { total: number; active: number; default: string }
  conversations: { total: number; today: number }
  system_health: { status: string; uptime_hours: number }
  recent_conversations: Array<{ id: string; title: string; created_at: string | null }>
}

interface HealthStatus {
  status: string
  database: { status: string; latency_ms: number }
  vector_store: { status: string; message?: string }
  default_llm: { status: string; model_name: string }
  sandbox: { status: string }
  search_engines: { total: number; active: number; default_name: string }
  timestamp: string
}

function StatusIndicator({ status }: { status: string | undefined }) {
  const color =
    status === 'connected' || status === 'available' || status === 'ready' || status === 'healthy'
      ? '#22c55e'
      : status === 'degraded' || status === 'unconfigured'
        ? '#f59e0b'
        : '#ef4444'
  return <span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: '50%', backgroundColor: color, marginRight: 8 }} />
}

export default function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [health, setHealth] = useState<HealthStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  async function fetchData() {
    setLoading(true)
    setError(null)
    try {
      const [statsRes, healthRes] = await Promise.all([
        adminApi.get('/dashboard/stats'),
        getHealthCheck(),
      ])
      setStats(statsRes.data.data)
      setHealth(healthRes.data.data)
    } catch (e) {
      setError(getErrorMessage(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
  }, [])

  if (loading) return <Loading text="加载 Dashboard 数据..." />
  if (error) {
    return (
      <div style={{ padding: 40, textAlign: 'center' }}>
        <p style={{ color: '#ef4444', marginBottom: 16 }}>{error}</p>
        <button onClick={fetchData} style={{ padding: '8px 16px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4 }}>
          <ICONS.refresh /> 重试
        </button>
      </div>
    )
  }

  const statCards = [
    { label: '模型', value: `${stats?.models.active ?? 0} / ${stats?.models.total ?? 0}`, sub: `默认: ${stats?.models.default || '—'}` },
    { label: '今日对话', value: `${stats?.conversations.today ?? 0} / ${stats?.conversations.total ?? 0}`, sub: '总对话数' },
    { label: '工具', value: `${stats?.tools.active ?? 0} / ${stats?.tools.total ?? 0}`, sub: `内置 ${stats?.tools.builtin ?? 0} · 自定义 ${stats?.tools.custom ?? 0}` },
    { label: '系统状态', value: stats?.system_health.status === 'healthy' ? 'Healthy' : 'Degraded', sub: '' },
  ]

  const healthRows = [
    { name: '数据库', item: health?.database },
    { name: '向量库', item: health?.vector_store },
    { name: 'LLM', item: health?.default_llm, extra: health?.default_llm.model_name },
    { name: '沙箱', item: health?.sandbox },
    { name: '搜索引擎', item: { status: health?.search_engines.active ? 'available' : 'unconfigured', latency_ms: 0 }, extra: `${health?.search_engines.active ?? 0} 活跃` },
  ]

  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0 }}>概览</h1>
        <button onClick={fetchData} style={{ padding: '8px 16px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}>
          <ICONS.refresh /> 刷新
        </button>
      </div>

      {/* Stat Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 16, marginBottom: 24 }}>
        {statCards.map((card) => (
          <div key={card.label} style={{ background: '#fff', borderRadius: 12, padding: 20, boxShadow: '0 1px 3px rgba(0,0,0,.1)', border: '1px solid #e5e7eb' }}>
            <div style={{ fontSize: 13, color: '#6b7280', marginBottom: 4 }}>{card.label}</div>
            <div style={{ fontSize: 28, fontWeight: 700 }}>{card.value}</div>
            {card.sub && <div style={{ fontSize: 12, color: '#9ca3af', marginTop: 4 }}>{card.sub}</div>}
          </div>
        ))}
      </div>

      {/* Health Panel */}
      <div style={{ background: '#fff', borderRadius: 12, padding: 20, marginBottom: 24, boxShadow: '0 1px 3px rgba(0,0,0,.1)', border: '1px solid #e5e7eb' }}>
        <h2 style={{ fontSize: 18, fontWeight: 600, margin: '0 0 16px' }}>系统健康状态</h2>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid #e5e7eb' }}>
              <th style={{ padding: '8px 12px', textAlign: 'left', fontSize: 13, color: '#6b7280' }}>组件</th>
              <th style={{ padding: '8px 12px', textAlign: 'left', fontSize: 13, color: '#6b7280' }}>状态</th>
              <th style={{ padding: '8px 12px', textAlign: 'left', fontSize: 13, color: '#6b7280' }}>延迟</th>
              <th style={{ padding: '8px 12px', textAlign: 'left', fontSize: 13, color: '#6b7280' }}>详情</th>
            </tr>
          </thead>
          <tbody>
            {healthRows.map((row) => (
              <tr key={row.name} style={{ borderBottom: '1px solid #f3f4f6' }}>
                <td style={{ padding: '10px 12px', fontWeight: 500 }}>{row.name}</td>
                <td style={{ padding: '10px 12px' }}>
                  <StatusIndicator status={row.item?.status} />
                  {row.item?.status ?? '—'}
                </td>
                <td style={{ padding: '10px 12px', color: '#6b7280' }}>
                  {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                  {(row.item as any)?.latency_ms ? `${(row.item as any).latency_ms}ms` : '—'}
                </td>
                <td style={{ padding: '10px 12px', color: '#6b7280', fontSize: 13 }}>
                  {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                  {row.extra || (row.item as any)?.message || '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {health?.timestamp && (
          <div style={{ fontSize: 12, color: '#9ca3af', marginTop: 12 }}>检查时间: {formatDateTime(health.timestamp)}</div>
        )}
      </div>

      {/* Recent Conversations */}
      <div style={{ background: '#fff', borderRadius: 12, padding: 20, boxShadow: '0 1px 3px rgba(0,0,0,.1)', border: '1px solid #e5e7eb' }}>
        <h2 style={{ fontSize: 18, fontWeight: 600, margin: '0 0 16px' }}>最近对话</h2>
        {stats?.recent_conversations.length ? (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #e5e7eb' }}>
                <th style={{ padding: '8px 12px', textAlign: 'left', fontSize: 13, color: '#6b7280' }}>标题</th>
                <th style={{ padding: '8px 12px', textAlign: 'left', fontSize: 13, color: '#6b7280' }}>时间</th>
              </tr>
            </thead>
            <tbody>
              {stats.recent_conversations.map((c) => (
                <tr key={c.id} style={{ borderBottom: '1px solid #f3f4f6' }}>
                  <td style={{ padding: '10px 12px' }}>{c.title || '未命名对话'}</td>
                  <td style={{ padding: '10px 12px', color: '#6b7280', fontSize: 13 }}>
                    {formatDateTime(c.created_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div style={{ textAlign: 'center', padding: 32, color: '#9ca3af' }}>暂无最近对话</div>
        )}
      </div>
    </div>
  )
}
