import { useMemo, useState } from 'react'
import Loading from '../components/ui/Loading.tsx'
import EmptyState from '../components/ui/EmptyState.tsx'
import { ICONS } from '../components/ui/Icons.tsx'
import { api } from '../api/client.ts'
import { getErrorMessage } from '../utils/errors.ts'
import { formatDateTime } from '../utils/format.ts'
import type { DataResponse } from '../types/report.ts'
import type { NLQueryResult, QueryHistoryItem } from '../types/query.ts'

// 示例问题，帮助新用户上手
const SUGGESTIONS = [
  '本月各科目借贷总额',
  '最近 30 天差旅费用排名前 10',
  '应收账款账龄分布',
  '本季度净利润同比变化',
]

const BACKEND_LABELS: Record<string, string> = {
  rule: '规则引擎',
  vanna: 'Vanna',
}

const HISTORY_KEY = 'finpilot:query-history'
const HISTORY_LIMIT = 5

function loadHistory(): QueryHistoryItem[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.slice(0, HISTORY_LIMIT) : []
  } catch {
    return []
  }
}

function saveHistory(items: QueryHistoryItem[]) {
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(items.slice(0, HISTORY_LIMIT)))
  } catch {
    // 忽略隐私模式或配额异常
  }
}

export default function QueriesPage() {
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<NLQueryResult | null>(null)
  const [history, setHistory] = useState<QueryHistoryItem[]>(loadHistory)

  const columns = useMemo(() => {
    if (!result?.data?.length) return []
    return Object.keys(result.data[0])
  }, [result])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const trimmed = question.trim()
    if (!trimmed || loading) return

    setLoading(true)
    setError('')
    setResult(null)
    try {
      const response = await api.post<DataResponse<NLQueryResult>>('/queries/nl2sql', {
        question: trimmed,
      })
      const data = response.data.data
      if (!data) {
        throw new Error('查询返回为空')
      }
      setResult(data)
      const next = [
        { question: trimmed, createdAt: new Date().toISOString(), ok: !data.error },
        ...loadHistory().filter((h) => h.question !== trimmed),
      ].slice(0, HISTORY_LIMIT)
      setHistory(next)
      saveHistory(next)
    } catch (err) {
      setError(getErrorMessage(err, '查询失败，请稍后重试'))
    } finally {
      setLoading(false)
    }
  }

  const pickSuggestion = (text: string) => {
    setQuestion(text)
  }

  const confidencePct = result?.confidence != null ? Math.round(result.confidence * 100) : null

  // 纯前端拼 CSV 下载：值含逗号/引号/换行则用双引号包裹并转义内部引号
  const handleExportCSV = () => {
    if (!result || result.data.length === 0) return
    const cols = columns
    const escapeCell = (value: unknown) => {
      const s = value === null || value === undefined ? '' : String(value)
      if (/[",\n\r]/.test(s)) {
        return `"${s.replace(/"/g, '""')}"`
      }
      return s
    }
    const lines = [
      cols.map(escapeCell).join(','),
      ...result.data.map((row) => cols.map((col) => escapeCell(row[col])).join(',')),
    ]
    // 加 UTF-8 BOM，避免 Excel 打开中文乱码
    const csv = '\uFEFF' + lines.join('\r\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const now = new Date()
    const pad = (n: number) => String(n).padStart(2, '0')
    const stamp = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}_${pad(now.getHours())}${pad(now.getMinutes())}`
    const link = document.createElement('a')
    link.href = url
    link.download = `查询结果_${stamp}.csv`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  }

  return (
    <div className="container">
      <div className="page-header">
        <div>
          <h1>财务数据查询</h1>
          <p className="text-muted text-sm">自然语言转SQL，实时检索财务报表与业务数据。</p>
        </div>
      </div>

      <div className="card query-input-card">
        <form onSubmit={handleSubmit} className="query-form">
          <input
            className="query-input"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="例如：本月各科目借贷总额是多少？"
            aria-label="自然语言问题"
            disabled={loading}
            autoFocus
          />
          <button type="submit" disabled={loading || !question.trim()}>
            {loading ? '查询中...' : '查询'}
          </button>
        </form>
        <div className="suggestion-chips">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              type="button"
              className="chip"
              onClick={() => pickSuggestion(s)}
              disabled={loading}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="alert alert-error mb-4" role="alert">
          {error}
        </div>
      )}

      {loading && <Loading text="正在生成 SQL 并执行查询..." />}

      {!loading && result && (
        <div className="query-result">
          {result.error ? (
            <div className="alert alert-warning mb-4" role="alert">
              这次没查出来：{result.error}
            </div>
          ) : (
            <>
              <div className="card">
                <div className="query-meta">
                  {result.sql && (
                    <span className="badge success">
                      {BACKEND_LABELS[result.backend || ''] || result.backend || '已生成'}
                    </span>
                  )}
                  {confidencePct != null && (
                    <span className="query-meta-item">置信度 {confidencePct}%</span>
                  )}
                  {result.execution_time_ms != null && (
                    <span className="query-meta-item">耗时 {result.execution_time_ms} ms</span>
                  )}
                  <button
                    type="button"
                    className="ghost"
                    style={{ marginLeft: 'auto' }}
                    onClick={handleExportCSV}
                    disabled={result.data.length === 0}
                    title="导出为 CSV"
                  >
                    <ICONS.download size={14} />
                    导出 CSV
                  </button>
                </div>
                {result.sql ? (
                  <pre className="code-block query-sql">{result.sql}</pre>
                ) : (
                  <p className="text-muted text-sm">未生成 SQL</p>
                )}
                {result.explanation && (
                  <p className="query-explanation">{result.explanation}</p>
                )}
              </div>

              {result.data.length > 0 ? (
                <div className="table-wrapper">
                  <table className="financial">
                    <thead>
                      <tr>
                        {columns.map((col) => (
                          <th key={col}>{col}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {result.data.map((row) => (
                        <tr key={columns.map((c) => row[c]).join('|')}>
                          {columns.map((col) => {
                            const v = row[col]
                            // 数值列右对齐 + 等宽数字，便于财务数据逐行对账
                            const isNum =
                              v !== null &&
                              v !== undefined &&
                              !Number.isNaN(Number(v)) &&
                              String(v).trim() !== ''
                            return (
                              <td key={col} className={isNum ? 'num' : undefined}>
                                {v === null || v === undefined ? (
                                  <span className="text-muted">—</span>
                                ) : (
                                  String(v)
                                )}
                              </td>
                            )
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <EmptyState title="查询结果为空" description="SQL 执行成功，但没有匹配的数据。" />
              )}
            </>
          )}
        </div>
      )}

      {!loading && !result && !error && history.length > 0 && (
        <div className="card">
          <h3 className="card-title">最近查询</h3>
          <ul className="activity-list">
            {history.map((h) => (
              <li key={`${h.question}-${h.createdAt}`}>
                <div className="activity-main">
                  <span className="activity-title">
                    <span className="activity-icon">{h.ok ? '✓' : '✕'}</span>
                    <button
                      type="button"
                      className="link query-history-link"
                      onClick={() => pickSuggestion(h.question)}
                    >
                      {h.question}
                    </button>
                  </span>
                  <span className="activity-time">
                    {formatDateTime(h.createdAt)}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
