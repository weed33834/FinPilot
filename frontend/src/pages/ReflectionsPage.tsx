import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client.ts'
import Loading from '../components/ui/Loading.tsx'
import Badge from '../components/ui/Badge.tsx'
import EmptyState from '../components/ui/EmptyState.tsx'
import Modal from '../components/ui/Modal.tsx'
import { getErrorMessage } from '../utils/errors.ts'
import { formatDateTime } from '../utils/format.ts'

interface Reflection {
  id: string
  created_at: string
  task_name: string | null
  task_id: string | null
  resource_type: string | null
  resource_id: string | null
  exception_type: string
  exception_message: string
  stack_trace: string | null
  error_category: string
  root_cause: string | null
  suggested_fix: string | null
  retried: boolean
  resolved: boolean
  resolution: string | null
}

interface PaginatedReflections {
  total: number
  page: number
  page_size: number
  items: Reflection[]
}

const CATEGORY_LABELS: Record<string, string> = {
  retryable: '可重试',
  business: '业务错误',
  config: '配置错误',
  security: '安全错误',
  unknown: '未知错误',
}

export default function ReflectionsPage() {
  const [data, setData] = useState<PaginatedReflections | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [page, setPage] = useState(1)
  const [category, setCategory] = useState('')
  const [resolved, setResolved] = useState('')
  const [selected, setSelected] = useState<Reflection | null>(null)
  const [resolution, setResolution] = useState('')
  const [resolving, setResolving] = useState(false)

  const fetchReflections = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const params: Record<string, string | number> = { page, page_size: 20 }
      if (category) params.category = category
      if (resolved) params.resolved = resolved
      const response = await api.get('/reflections', { params })
      setData(response.data.data)
    } catch (err) {
      setError(getErrorMessage(err, '加载自省日志失败'))
    } finally {
      setLoading(false)
    }
  }, [page, category, resolved])

  useEffect(() => {
    fetchReflections()
  }, [fetchReflections])

  const handleResolve = async () => {
    if (!selected || !resolution.trim() || resolving) return
    setResolving(true)
    try {
      await api.post(`/reflections/${selected.id}/resolve`, { resolution: resolution.trim() })
      setSelected(null)
      setResolution('')
      fetchReflections()
    } catch (err) {
      setError(getErrorMessage(err, '标记解决失败'))
    } finally {
      setResolving(false)
    }
  }

  return (
    <div className="container">
      <div className="page-header">
        <div>
          <h1>错误自省</h1>
          <p className="text-muted text-sm">看看任务失败的模式、根因和修复建议</p>
        </div>
      </div>

      {error && (
        <div className="alert alert-error mb-4" role="alert">
          {error}
        </div>
      )}

      <div className="card mb-4">
        <div className="filters">
          <div className="form-group">
            <label htmlFor="reflection-category">错误分类</label>
            <select id="reflection-category" value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="">全部</option>
              {Object.entries(CATEGORY_LABELS).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </div>
          <div className="form-group">
            <label htmlFor="reflection-resolved">解决状态</label>
            <select id="reflection-resolved" value={resolved} onChange={(e) => setResolved(e.target.value)}>
              <option value="">全部</option>
              <option value="false">未解决</option>
              <option value="true">已解决</option>
            </select>
          </div>
        </div>
      </div>

      {loading ? (
        <Loading text="加载自省日志..." />
      ) : data && data.items.length > 0 ? (
        <>
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>时间</th>
                  <th>任务</th>
                  <th>资源</th>
                  <th>异常类型</th>
                  <th>分类</th>
                  <th>状态</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((item) => (
                  <tr key={item.id}>
                    <td>{formatDateTime(item.created_at)}</td>
                    <td>{item.task_name || '-'}</td>
                    <td>
                      {item.resource_type || '-'} {item.resource_id ? `(${item.resource_id.slice(0, 8)})` : ''}
                    </td>
                    <td>{item.exception_type}</td>
                    <td>{CATEGORY_LABELS[item.error_category] || item.error_category}</td>
                    <td>
                      <Badge status={item.resolved ? 'approved' : 'reviewing'} />
                    </td>
                    <td>
                      <button type="button" className="btn secondary" onClick={() => setSelected(item)}>
                        详情
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="pagination">
            <button
              type="button"
              className="btn secondary"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
            >
              上一页
            </button>
            <span className="text-sm">
              第 {data.page} 页 / 共 {Math.ceil(data.total / data.page_size)} 页（{data.total} 条）
            </span>
            <button
              type="button"
              className="btn secondary"
              disabled={page * data.page_size >= data.total}
              onClick={() => setPage((p) => p + 1)}
            >
              下一页
            </button>
          </div>
        </>
      ) : (
        <EmptyState title="暂无错误自省日志" description="当前没有任务失败或异常记录。" />
      )}

      {selected && (
        <Modal title="自省详情" onClose={() => setSelected(null)}>
          {error && <div className="alert alert-error mb-3">{error}</div>}
          <div className="detail-group">
            <span className="detail-label">异常消息</span>
            <p>{selected.exception_message}</p>
          </div>
          <div className="detail-group">
            <span className="detail-label">根因分析</span>
            <p>{selected.root_cause || '暂无'}</p>
          </div>
          <div className="detail-group">
            <span className="detail-label">修复建议</span>
            <p>{selected.suggested_fix || '暂无'}</p>
          </div>
          {selected.stack_trace && (
            <div className="detail-group">
              <span className="detail-label">堆栈</span>
              <pre className="code-block">{selected.stack_trace}</pre>
            </div>
          )}
          {!selected.resolved && (
            <div className="detail-group">
              <span className="detail-label">解决方案</span>
              <div className="form-group">
                <textarea
                  rows={3}
                  value={resolution}
                  onChange={(e) => setResolution(e.target.value)}
                  placeholder="记录如何解决该问题..."
                />
              </div>
              <button type="button" className="btn mt-4" onClick={handleResolve} disabled={resolving || !resolution.trim()}>
                {resolving ? '提交中...' : '标记已解决'}
              </button>
            </div>
          )}
          {selected.resolved && selected.resolution && (
            <div className="detail-group">
              <span className="detail-label">已记录方案</span>
              <p>{selected.resolution}</p>
            </div>
          )}
        </Modal>
      )}
    </div>
  )
}
