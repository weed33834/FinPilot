import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client.ts'
import Loading from '../components/ui/Loading.tsx'
import Badge from '../components/ui/Badge.tsx'
import EmptyState from '../components/ui/EmptyState.tsx'
import Modal from '../components/ui/Modal.tsx'
import { toast } from '../components/ui/Toaster.tsx'
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

const CATEGORY_KEYS: Record<string, string> = {
  retryable: 'common:reflections.categoryRetryable',
  business: 'common:reflections.categoryBusiness',
  config: 'common:reflections.categoryConfig',
  security: 'common:reflections.categorySecurity',
  unknown: 'common:reflections.categoryUnknown',
}

export default function ReflectionsPage() {
  const { t } = useTranslation()
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
      setError(getErrorMessage(err, t('common:reflections.loadFailed')))
    } finally {
      setLoading(false)
    }
  }, [page, category, resolved, t])

  useEffect(() => {
    fetchReflections()
  }, [fetchReflections])

  // 切换筛选条件时重置到第一页，避免查看空页
  const handleCategoryChange = (value: string) => {
    setCategory(value)
    setPage(1)
  }
  const handleResolvedChange = (value: string) => {
    setResolved(value)
    setPage(1)
  }

  const handleResolve = async () => {
    if (!selected || !resolution.trim() || resolving) return
    setResolving(true)
    try {
      await api.post(`/reflections/${selected.id}/resolve`, { resolution: resolution.trim() })
      toast.success(t('common:reflections.toastResolved'))
      setSelected(null)
      setResolution('')
      fetchReflections()
    } catch (err) {
      toast.error(getErrorMessage(err, t('common:reflections.resolveFailed')))
    } finally {
      setResolving(false)
    }
  }

  const categoryLabel = (key: string) => {
    const k = CATEGORY_KEYS[key]
    return k ? t(k) : key
  }

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1

  return (
    <div className="container">
      <div className="page-header">
        <div>
          <h1>{t('common:reflections.title')}</h1>
          <p className="text-muted text-sm">{t('common:reflections.subtitle')}</p>
        </div>
      </div>

      {error && (
        <div className="alert alert-error mb-4" role="alert">
          <span>{error}</span>
          <button type="button" className="chat-error-retry" onClick={fetchReflections}>
            {t('common:reflections.retry')}
          </button>
        </div>
      )}

      <div className="card mb-4">
        <div className="filters">
          <div className="form-group">
            <label htmlFor="reflection-category">{t('common:reflections.filterCategory')}</label>
            <select
              id="reflection-category"
              value={category}
              onChange={(e) => handleCategoryChange(e.target.value)}
            >
              <option value="">{t('common:reflections.all')}</option>
              {Object.entries(CATEGORY_KEYS).map(([key]) => (
                <option key={key} value={key}>
                  {categoryLabel(key)}
                </option>
              ))}
            </select>
          </div>
          <div className="form-group">
            <label htmlFor="reflection-resolved">{t('common:reflections.filterResolved')}</label>
            <select
              id="reflection-resolved"
              value={resolved}
              onChange={(e) => handleResolvedChange(e.target.value)}
            >
              <option value="">{t('common:reflections.all')}</option>
              <option value="false">{t('common:reflections.resolvedFalse')}</option>
              <option value="true">{t('common:reflections.resolvedTrue')}</option>
            </select>
          </div>
        </div>
      </div>

      {loading ? (
        <Loading text={t('common:reflections.loading')} />
      ) : data && data.items.length > 0 ? (
        <>
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>{t('common:reflections.colTime')}</th>
                  <th>{t('common:reflections.colTask')}</th>
                  <th>{t('common:reflections.colResource')}</th>
                  <th>{t('common:reflections.colException')}</th>
                  <th>{t('common:reflections.colCategory')}</th>
                  <th>{t('common:reflections.colStatus')}</th>
                  <th>{t('common:reflections.colActions')}</th>
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
                    <td>{categoryLabel(item.error_category)}</td>
                    <td>
                      <Badge status={item.resolved ? 'approved' : 'reviewing'} />
                    </td>
                    <td>
                      <button type="button" className="btn secondary" onClick={() => setSelected(item)}>
                        {t('common:reflections.detail')}
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
              {t('common:reflections.prevPage')}
            </button>
            <span className="text-sm">
              {t('common:reflections.pageInfo', { page: data.page, total: totalPages, count: data.total })}
            </span>
            <button
              type="button"
              className="btn secondary"
              disabled={page * data.page_size >= data.total}
              onClick={() => setPage((p) => p + 1)}
            >
              {t('common:reflections.nextPage')}
            </button>
          </div>
        </>
      ) : (
        <EmptyState
          title={t('common:reflections.emptyTitle')}
          description={t('common:reflections.emptyDesc')}
          action={
            <button type="button" className="secondary" onClick={fetchReflections}>
              {t('common:reflections.retry')}
            </button>
          }
        />
      )}

      {selected && (
        <Modal title={t('common:reflections.detailTitle')} onClose={() => setSelected(null)}>
          {error && <div className="alert alert-error mb-3">{error}</div>}
          <div className="detail-group">
            <span className="detail-label">{t('common:reflections.exceptionMessage')}</span>
            <p>{selected.exception_message}</p>
          </div>
          <div className="detail-group">
            <span className="detail-label">{t('common:reflections.rootCause')}</span>
            <p>{selected.root_cause || t('common:reflections.none')}</p>
          </div>
          <div className="detail-group">
            <span className="detail-label">{t('common:reflections.suggestedFix')}</span>
            <p>{selected.suggested_fix || t('common:reflections.none')}</p>
          </div>
          {selected.stack_trace && (
            <div className="detail-group">
              <span className="detail-label">{t('common:reflections.stackTrace')}</span>
              <pre className="code-block">{selected.stack_trace}</pre>
            </div>
          )}
          {!selected.resolved && (
            <div className="detail-group">
              <span className="detail-label">{t('common:reflections.solution')}</span>
              <div className="form-group">
                <textarea
                  rows={3}
                  value={resolution}
                  onChange={(e) => setResolution(e.target.value)}
                  placeholder={t('common:reflections.solutionPlaceholder')}
                />
              </div>
              <button
                type="button"
                className="btn mt-4"
                onClick={handleResolve}
                disabled={resolving || !resolution.trim()}
              >
                {resolving ? t('common:reflections.resolving') : t('common:reflections.markResolved')}
              </button>
            </div>
          )}
          {selected.resolved && selected.resolution && (
            <div className="detail-group">
              <span className="detail-label">{t('common:reflections.resolvedRecord')}</span>
              <p>{selected.resolution}</p>
            </div>
          )}
        </Modal>
      )}
    </div>
  )
}
