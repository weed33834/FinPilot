import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import i18n from '../../i18n/config.ts'
import zhCNAdminContext from '../../i18n/locales/zh-CN/admin-context.json'
import enAdminContext from '../../i18n/locales/en/admin-context.json'
import EmptyState from '../../components/ui/EmptyState.tsx'
import { confirm } from '../../components/ui/ConfirmDialog.tsx'
import { ICONS } from '../../components/ui/Icons.tsx'
import { getErrorMessage } from '../../utils/errors.ts'
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

// adminContext 命名空间未在 i18n/config.ts 中注册（按要求不修改该文件），
// 在模块加载时同步注入资源，子组件通过 useTranslation('adminContext') 消费。
const NS = 'adminContext'
if (!i18n.hasResourceBundle('zh-CN', NS)) {
  i18n.addResourceBundle('zh-CN', NS, zhCNAdminContext)
}
if (!i18n.hasResourceBundle('en', NS)) {
  i18n.addResourceBundle('en', NS, enAdminContext)
}

type Tab = 'tokens' | 'memories' | 'stats'

// 模型标识为专有名词，仅「默认模型」需翻译；枚举值原样提交给 API。
const MODELS = ['', 'gpt-4o', 'gpt-4o-mini', 'gpt-3.5-turbo', 'claude-3-5-sonnet', 'deepseek-chat']

// 分类枚举值原样提交给 API，仅展示 label 走 i18n。
const CATEGORIES = ['', 'preference', 'fact', 'instruction', 'summary', 'other']

/* ------------------------------------------------------------------ */
/*  Token 计数器                                                        */
/* ------------------------------------------------------------------ */

function TokenCounter() {
  const { t } = useTranslation(NS)
  const [text, setText] = useState('')
  const [model, setModel] = useState('')
  const [result, setResult] = useState<TokenCountResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [retryTick, setRetryTick] = useState(0)
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
          setError(getErrorMessage(e, t('token.calcFailed')))
        }
      } finally {
        if (current === reqId.current) setLoading(false)
      }
    }, 400)
    return () => window.clearTimeout(timer)
  }, [text, model, retryTick, t])

  return (
    <div className="admin-card" style={{ padding: 20, maxWidth: 820 }}>
      <div className="admin-form-row" style={{ marginBottom: 12 }}>
        <label className="admin-form-label">{t('token.modelLabel')}</label>
        <select
          className="admin-form-select"
          value={model}
          onChange={(e) => setModel(e.target.value)}
          style={{ maxWidth: 260 }}
        >
          {MODELS.map((m) => (
            <option key={m} value={m}>
              {m === '' ? t('token.models.default') : m}
            </option>
          ))}
        </select>
      </div>

      <textarea
        className="admin-form-textarea"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={t('token.placeholder')}
        style={{ minHeight: 200, fontFamily: 'var(--font-mono, monospace)' }}
      />

      <div style={{ display: 'flex', gap: 24, marginTop: 16, alignItems: 'center' }}>
        <div>
          <div style={{ fontSize: '0.72rem', color: 'var(--color-text-muted,#9aa)' }}>{t('token.tokenCount')}</div>
          <div style={{ fontSize: '1.8rem', fontWeight: 700, color: 'var(--color-primary,#3b82f6)' }}>
            {loading ? '…' : result?.token_count ?? 0}
          </div>
        </div>
        <div>
          <div style={{ fontSize: '0.72rem', color: 'var(--color-text-muted,#9aa)' }}>{t('token.charCount')}</div>
          <div style={{ fontSize: '1.8rem', fontWeight: 700 }}>
            {result?.char_count ?? text.length}
          </div>
        </div>
        {result?.model && (
          <div>
            <div style={{ fontSize: '0.72rem', color: 'var(--color-text-muted,#9aa)' }}>{t('token.estimatedModel')}</div>
            <div style={{ fontSize: '0.9rem', marginTop: 6 }}>{String(result.model)}</div>
          </div>
        )}
      </div>

      {error && (
        <div className="admin-error" style={{ marginTop: 12, display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ flex: 1 }}>{error}</span>
          <button
            type="button"
            className="btn btn-secondary"
            style={{ padding: '2px 8px', fontSize: '0.72rem' }}
            onClick={() => setRetryTick((n) => n + 1)}
          >
            {t('actions.retry')}
          </button>
        </div>
      )}
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
  const { t } = useTranslation(NS)
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
      setError(getErrorMessage(e, t('memories.messages.loadFailed')))
    } finally {
      setLoading(false)
    }
  }, [query, category, t])

  useEffect(() => {
    void load()
  }, [load])

  const handleDelete = async (id: string) => {
    const ok = await confirm({
      title: t('memories.confirm.deleteTitle'),
      message: t('memories.confirm.deleteMessage'),
      confirmText: t('actions.confirm'),
      cancelText: t('actions.cancel'),
      variant: 'danger',
    })
    if (!ok) return
    try {
      await deleteMemory(id)
      setMemories((prev) => prev.filter((m) => m.id !== id))
    } catch (e) {
      setError(getErrorMessage(e, t('memories.messages.deleteFailed')))
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
          placeholder={t('memories.searchPlaceholder')}
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
              {c === '' ? t('memories.categories.all') : t(`memories.categories.${c}`, { defaultValue: c })}
            </option>
          ))}
        </select>
        <button className="btn btn-primary" onClick={() => void load()} disabled={loading}>
          <ICONS.search size={14} />
          {loading ? t('memories.actions.searching') : t('memories.actions.search')}
        </button>
      </div>

      {error && (
        <div className="admin-error" style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ flex: 1 }}>{error}</span>
          <button
            type="button"
            className="btn btn-secondary"
            style={{ padding: '2px 8px', fontSize: '0.72rem' }}
            onClick={() => void load()}
          >
            {t('actions.retry')}
          </button>
        </div>
      )}

      <div className="admin-table-wrapper">
        <table className="admin-table">
          <thead>
            <tr>
              <th>{t('memories.table.content')}</th>
              <th style={{ width: 110 }}>{t('memories.table.category')}</th>
              <th style={{ width: 90 }}>{t('memories.table.importance')}</th>
              <th style={{ width: 150 }}>{t('memories.table.sourceConversation')}</th>
              <th style={{ width: 160 }}>{t('memories.table.createdAt')}</th>
              <th style={{ width: 80 }}>{t('memories.table.actions')}</th>
            </tr>
          </thead>
          <tbody>
            {memories.length === 0 && !loading ? (
              <tr>
                <td colSpan={6}>
                  <EmptyState title={t('memories.empty')} size="sm" />
                </td>
              </tr>
            ) : (
              memories.map((m) => {
                const cat = m.category ?? null
                return (
                  <tr key={m.id}>
                    <td style={{ maxWidth: 360, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                      {String(m.content ?? '')}
                    </td>
                    <td>
                      <span className="badge">
                        {cat ? t(`memories.categories.${cat}`, { defaultValue: cat }) : '-'}
                      </span>
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
                        {t('memories.actions.delete')}
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
/*  上下文统计                                                          */
/* ------------------------------------------------------------------ */

function StatsPanel() {
  const { t } = useTranslation(NS)
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
      setError(getErrorMessage(e, t('stats.messages.loadFailed')))
    } finally {
      setLoading(false)
    }
  }, [t])

  useEffect(() => {
    void load()
  }, [load])

  const cards: { label: string; value: string | number }[] = []
  if (stats) {
    if (stats.total_memories != null)
      cards.push({ label: t('stats.cards.total_memories'), value: stats.total_memories })
    if (stats.total_conversations != null)
      cards.push({ label: t('stats.cards.total_conversations'), value: stats.total_conversations })
    if (stats.avg_tokens_per_conversation != null)
      cards.push({
        label: t('stats.cards.avg_tokens_per_conversation'),
        value: Math.round(Number(stats.avg_tokens_per_conversation)),
      })
    // 渲染其余数值字段
    for (const [k, v] of Object.entries(stats)) {
      if (['total_memories', 'total_conversations', 'avg_tokens_per_conversation'].includes(k))
        continue
      if (typeof v === 'number') cards.push({ label: t(`stats.cards.${k}`, { defaultValue: k }), value: v })
    }
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
        <button className="btn btn-secondary" onClick={() => void load()} disabled={loading}>
          <ICONS.refresh size={14} />
          {t('stats.actions.refresh')}
        </button>
      </div>
      {error && (
        <div className="admin-error" style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ flex: 1 }}>{error}</span>
          <button
            type="button"
            className="btn btn-secondary"
            style={{ padding: '2px 8px', fontSize: '0.72rem' }}
            onClick={() => void load()}
          >
            {t('actions.retry')}
          </button>
        </div>
      )}
      {loading && !stats ? (
        <div style={{ padding: 32, textAlign: 'center', color: '#9aa' }}>{t('stats.loading')}</div>
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
            gap: 14,
          }}
        >
          {cards.length === 0 ? (
            <EmptyState title={t('stats.empty')} size="sm" />
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
  const { t } = useTranslation(NS)
  const [tab, setTab] = useState<Tab>('tokens')
  return (
    <div>
      <div className="admin-page-header">
        <h1 className="admin-page-title">{t('title')}</h1>
        <p className="admin-page-desc">{t('description')}</p>
      </div>

      <div className="tabs">
        <button
          className={`tab-item${tab === 'tokens' ? ' active' : ''}`}
          onClick={() => setTab('tokens')}
        >
          {t('tabs.tokens')}
        </button>
        <button
          className={`tab-item${tab === 'memories' ? ' active' : ''}`}
          onClick={() => setTab('memories')}
        >
          {t('tabs.memories')}
        </button>
        <button
          className={`tab-item${tab === 'stats' ? ' active' : ''}`}
          onClick={() => setTab('stats')}
        >
          {t('tabs.stats')}
        </button>
      </div>

      {tab === 'tokens' && <TokenCounter />}
      {tab === 'memories' && <MemoriesPanel />}
      {tab === 'stats' && <StatsPanel />}
    </div>
  )
}
