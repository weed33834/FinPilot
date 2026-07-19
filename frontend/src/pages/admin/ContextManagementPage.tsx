import { useCallback, useEffect, useRef, useState } from 'react'
import {
  countTokens,
  deleteMemory,
  getContextStats,
  getMemories,
  searchMemories,
  type ContextStats,
  type MemoryItem,
  type TokenCountResult,
} from '../../api/contextManager.ts'
import { ICONS } from '../../components/ui/Icons.tsx'

type Tab = 'tokens' | 'memories' | 'stats'

const MODELS = [
  { value: '', label: '默认模型' },
  { value: 'gpt-4o', label: 'gpt-4o' },
  { value: 'gpt-4o-mini', label: 'gpt-4o-mini' },
  { value: 'gpt-3.5-turbo', label: 'gpt-3.5-turbo' },
  { value: 'claude-3-5-sonnet', label: 'claude-3-5-sonnet' },
  { value: 'deepseek-chat', label: 'deepseek-chat' },
]

const CATEGORIES = ['', 'preference', 'fact', 'instruction', 'summary', 'other']

/* ------------------------------------------------------------------ */
/*  Token 计数器                                                        */
/* ------------------------------------------------------------------ */

function TokenCounter() {
  const [text, setText] = useState('')
  const [model, setModel] = useState('')
  const [result, setResult] = useState<TokenCountResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const reqId = useRef(0)

  useEffect(() => {
    if (!text.trim()) {
      setResult(null)
      setError(null)
      return
    }
    const current = ++reqId.current
    const timer = window.setTimeout(async () => {
      setLoading(true)
      setError(null)
      try {
        const env = await countTokens(text, model || undefined)
        if (current === reqId.current) {
          setResult(env.data)
        }
      } catch (e) {
        if (current === reqId.current) {
          setError(e instanceof Error ? e.message : '计算失败')
        }
      } finally {
        if (current === reqId.current) setLoading(false)
      }
    }, 400)
    return () => window.clearTimeout(timer)
  }, [text, model])

  return (
    <div className="admin-card" style={{ padding: 20, maxWidth: 820 }}>
      <div className="admin-form-row" style={{ marginBottom: 12 }}>
        <label className="admin-form-label">模型</label>
        <select
          className="admin-form-select"
          value={model}
          onChange={(e) => setModel(e.target.value)}
          style={{ maxWidth: 260 }}
        >
          {MODELS.map((m) => (
            <option key={m.value} value={m.value}>
              {m.label}
            </option>
          ))}
        </select>
      </div>

      <textarea
        className="admin-form-textarea"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="粘贴或输入文本，实时计算 Token 数量…"
        style={{ minHeight: 200, fontFamily: 'var(--font-mono, monospace)' }}
      />

      <div style={{ display: 'flex', gap: 24, marginTop: 16, alignItems: 'center' }}>
        <div>
          <div style={{ fontSize: '0.72rem', color: 'var(--color-text-muted,#9aa)' }}>Token 数</div>
          <div style={{ fontSize: '1.8rem', fontWeight: 700, color: 'var(--color-primary,#3b82f6)' }}>
            {loading ? '…' : result?.token_count ?? 0}
          </div>
        </div>
        <div>
          <div style={{ fontSize: '0.72rem', color: 'var(--color-text-muted,#9aa)' }}>字符数</div>
          <div style={{ fontSize: '1.8rem', fontWeight: 700 }}>
            {result?.char_count ?? text.length}
          </div>
        </div>
        {result?.model && (
          <div>
            <div style={{ fontSize: '0.72rem', color: 'var(--color-text-muted,#9aa)' }}>估算模型</div>
            <div style={{ fontSize: '0.9rem', marginTop: 6 }}>{String(result.model)}</div>
          </div>
        )}
      </div>

      {error && <div className="admin-error" style={{ marginTop: 12 }}>{error}</div>}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  长期记忆                                                            */
/* ------------------------------------------------------------------ */

function importanceBadge(v: number | null | undefined) {
  if (v == null) return <span className="badge">-</span>
  const level = v >= 8 ? 'high' : v >= 5 ? 'mid' : 'low'
  const color =
    level === 'high' ? '#ef4444' : level === 'mid' ? '#eab308' : '#64748b'
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        fontSize: '0.72rem',
        color,
      }}
    >
      <span
        style={{
          width: 6,
          height: 6,
          borderRadius: '50%',
          background: color,
        }}
      />
      {v}
    </span>
  )
}

function MemoriesPanel() {
  const [memories, setMemories] = useState<MemoryItem[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      let env
      if (query.trim()) {
        env = await searchMemories(query.trim())
      } else {
        env = await getMemories(undefined, category || undefined)
      }
      const list = env.data ?? []
      setMemories(list)
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [query, category])

  useEffect(() => {
    void load()
  }, [load])

  const handleDelete = async (id: string) => {
    if (!window.confirm('确认删除该长期记忆？')) return
    try {
      await deleteMemory(id)
      setMemories((prev) => prev.filter((m) => m.id !== id))
    } catch (e) {
      setError(e instanceof Error ? e.message : '删除失败')
    }
  }

  return (
    <div>
      <div
        style={{
          display: 'flex',
          gap: 10,
          alignItems: 'center',
          marginBottom: 14,
          flexWrap: 'wrap',
        }}
      >
        <input
          className="admin-form-input"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="语义搜索记忆内容…"
          style={{ maxWidth: 320 }}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void load()
          }}
        />
        <select
          className="admin-form-select"
          value={category}
          onChange={(e) => {
            setCategory(e.target.value)
            setQuery('')
          }}
          style={{ maxWidth: 180 }}
        >
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {c === '' ? '全部分类' : c}
            </option>
          ))}
        </select>
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
              <th>内容</th>
              <th style={{ width: 110 }}>分类</th>
              <th style={{ width: 90 }}>重要性</th>
              <th style={{ width: 150 }}>来源会话</th>
              <th style={{ width: 160 }}>创建时间</th>
              <th style={{ width: 80 }}>操作</th>
            </tr>
          </thead>
          <tbody>
            {memories.length === 0 && !loading ? (
              <tr>
                <td colSpan={6} style={{ textAlign: 'center', padding: 32, color: '#9aa' }}>
                  暂无长期记忆
                </td>
              </tr>
            ) : (
              memories.map((m) => (
                <tr key={m.id}>
                  <td style={{ maxWidth: 360, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                    {String(m.content ?? '')}
                  </td>
                  <td>
                    <span className="badge">{String(m.category ?? '-')}</span>
                  </td>
                  <td>{importanceBadge(m.importance)}</td>
                  <td className="admin-table-mono" style={{ fontSize: '0.72rem' }}>
                    {m.source_conversation_id ? String(m.source_conversation_id).slice(0, 8) : '-'}
                  </td>
                  <td style={{ fontSize: '0.72rem', color: '#9aa' }}>
                    {m.created_at ? new Date(String(m.created_at)).toLocaleString() : '-'}
                  </td>
                  <td>
                    <button
                      className="btn btn-danger"
                      style={{ padding: '2px 8px', fontSize: '0.72rem' }}
                      onClick={() => void handleDelete(m.id)}
                    >
                      删除
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  上下文统计                                                          */
/* ------------------------------------------------------------------ */

function StatsPanel() {
  const [stats, setStats] = useState<ContextStats | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const env = await getContextStats()
      setStats(env.data)
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const cards: { label: string; value: string | number }[] = []
  if (stats) {
    if (stats.total_memories != null)
      cards.push({ label: '记忆总数', value: stats.total_memories })
    if (stats.total_conversations != null)
      cards.push({ label: '会话总数', value: stats.total_conversations })
    if (stats.avg_tokens_per_conversation != null)
      cards.push({
        label: '平均 Token / 会话',
        value: Math.round(Number(stats.avg_tokens_per_conversation)),
      })
    // 渲染其余数值字段
    for (const [k, v] of Object.entries(stats)) {
      if (['total_memories', 'total_conversations', 'avg_tokens_per_conversation'].includes(k))
        continue
      if (typeof v === 'number') cards.push({ label: k, value: v })
    }
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
        <button className="btn btn-secondary" onClick={() => void load()} disabled={loading}>
          <ICONS.refresh size={14} />
          刷新
        </button>
      </div>
      {error && <div className="admin-error" style={{ marginBottom: 12 }}>{error}</div>}
      {loading && !stats ? (
        <div style={{ padding: 32, textAlign: 'center', color: '#9aa' }}>加载中…</div>
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
            gap: 14,
          }}
        >
          {cards.length === 0 ? (
            <div style={{ color: '#9aa' }}>暂无统计数据</div>
          ) : (
            cards.map((c) => (
              <div
                key={c.label}
                className="admin-card"
                style={{ padding: 18, borderRadius: 10 }}
              >
                <div style={{ fontSize: '0.74rem', color: 'var(--color-text-muted,#9aa)' }}>
                  {c.label}
                </div>
                <div style={{ fontSize: '1.6rem', fontWeight: 700, marginTop: 6 }}>{c.value}</div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  页面                                                                */
/* ------------------------------------------------------------------ */

export default function ContextManagementPage() {
  const [tab, setTab] = useState<Tab>('tokens')
  return (
    <div>
      <div className="admin-page-header">
        <h1 className="admin-page-title">上下文管理</h1>
        <p className="admin-page-desc">Token 计数、长期记忆与上下文使用统计</p>
      </div>

      <div className="tabs">
        <button
          className={`tab-item${tab === 'tokens' ? ' active' : ''}`}
          onClick={() => setTab('tokens')}
        >
          Token 计数器
        </button>
        <button
          className={`tab-item${tab === 'memories' ? ' active' : ''}`}
          onClick={() => setTab('memories')}
        >
          长期记忆
        </button>
        <button
          className={`tab-item${tab === 'stats' ? ' active' : ''}`}
          onClick={() => setTab('stats')}
        >
          上下文统计
        </button>
      </div>

      {tab === 'tokens' && <TokenCounter />}
      {tab === 'memories' && <MemoriesPanel />}
      {tab === 'stats' && <StatsPanel />}
    </div>
  )
}
