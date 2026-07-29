import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import { getErrorMessage } from '../utils/errors'
import type { AuditLog } from '../types/audit'
import AuditLogList from '../components/AuditLogList'
import Loading from '../components/ui/Loading.tsx'
import EmptyState from '../components/ui/EmptyState.tsx'
import { ICONS } from '../components/ui/Icons.tsx'

interface AuditPaginatedResponse {
  total: number
  page: number
  page_size: number
  items: AuditLog[]
}

export default function AuditPage() {
  const { t } = useTranslation()
  const [logs, setLogs] = useState<AuditLog[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [keyword, setKeyword] = useState('')
  const [resultFilter, setResultFilter] = useState('')

  const fetchLogs = async () => {
    setLoading(true)
    setError('')
    try {
      const response = await api.get<{ data: AuditPaginatedResponse }>('/audit/logs', {
        params: { page: 1, page_size: 100 },
      })
      setLogs(response.data.data?.items || [])
    } catch (err) {
      setError(getErrorMessage(err, t('common:audit.loadFailed')))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchLogs()
  }, [])

  // 客户端关键词 + 结果过滤
  const filteredLogs = useMemo(() => {
    let list = logs
    if (resultFilter) {
      const wantSuccess = resultFilter === 'success'
      list = list.filter((l) => {
        const r = (l.result || '').toLowerCase()
        return wantSuccess ? r.includes('success') || r === '' : r.includes('fail')
      })
    }
    const kw = keyword.trim().toLowerCase()
    if (kw) {
      list = list.filter((l) =>
        [l.action, l.resource, l.ip, l.reason].some((v) => (v || '').toLowerCase().includes(kw)),
      )
    }
    return list
  }, [logs, keyword, resultFilter])

  return (
    <div className="container">
      <div className="page-header">
        <div>
          <h1>{t('common:audit.title')}</h1>
          <p className="text-muted text-sm">{t('common:audit.subtitle')}</p>
        </div>
        <button type="button" className="secondary" onClick={fetchLogs}>
          {t('common:audit.refresh')}
        </button>
      </div>

      {error && (
        <div className="alert alert-error mb-4" role="alert">
          <span>{error}</span>
          <button type="button" className="chat-error-retry" onClick={fetchLogs}>
            {t('common:audit.retry')}
          </button>
        </div>
      )}

      <div className="toolbar">
        <div className="form-group">
          <label htmlFor="audit-result-filter">{t('common:audit.filterResult')}</label>
          <select
            id="audit-result-filter"
            value={resultFilter}
            onChange={(e) => setResultFilter(e.target.value)}
          >
            <option value="">{t('common:audit.resultAll')}</option>
            <option value="success">{t('common:audit.resultSuccess')}</option>
            <option value="failed">{t('common:audit.resultFailed')}</option>
          </select>
        </div>
        {logs.length > 0 && (
          <div className="search-inline">
            <ICONS.search size={14} />
            <input
              type="search"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              placeholder={t('common:audit.searchPlaceholder')}
              aria-label={t('common:audit.searchPlaceholder')}
            />
          </div>
        )}
      </div>

      {loading ? (
        <Loading text={t('common:audit.loading')} />
      ) : logs.length === 0 ? (
        <EmptyState
          icon="audit"
          title={t('common:audit.emptyTitle')}
          description={t('common:audit.emptyDesc')}
          action={
            <button type="button" className="secondary" onClick={fetchLogs}>
              {t('common:audit.refresh')}
            </button>
          }
        />
      ) : filteredLogs.length === 0 ? (
        <EmptyState
          icon="search"
          title={t('common:audit.emptySearchTitle')}
          description={t('common:audit.emptySearchDesc')}
        />
      ) : (
        <AuditLogList logs={filteredLogs} />
      )}
    </div>
  )
}
