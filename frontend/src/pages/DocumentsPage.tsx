import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router-dom'
import { api } from '../api/client'
import { getErrorMessage } from '../utils/errors'
import type { Document } from '../types/document'
import type { DataResponse, PaginatedResponse } from '../types/report'
import DocumentDetail from '../components/DocumentDetail'
import DocumentList from '../components/DocumentList'
import DocumentUpload from '../components/DocumentUpload'
import Loading from '../components/ui/Loading.tsx'
import EmptyState from '../components/ui/EmptyState.tsx'
import Badge from '../components/ui/Badge.tsx'
import { ICONS } from '../components/ui/Icons.tsx'
import { toast } from '../components/ui/Toaster.tsx'
import { useDevice } from '../context/DeviceContext'
import DocumentsMobile from './mobile/DocumentsMobile'
import DocumentDetailMobile from './mobile/DocumentDetailMobile'

export default function DocumentsPage() {
  const { t } = useTranslation()
  const { id } = useParams<{ id: string }>()
  const { isMobile } = useDevice()
  if (isMobile) return id ? <DocumentDetailMobile id={id} /> : <DocumentsMobile />
  const [documents, setDocuments] = useState<Document[]>([])
  const [selected, setSelected] = useState<Document | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [status, setStatus] = useState('')
  const [keyword, setKeyword] = useState('')

  const statusOptions = useMemo(
    () => [
      { value: '', label: t('common:documents.statusAll') },
      { value: 'pending', label: t('common:documents.statusPending') },
      { value: 'processing', label: t('common:documents.statusProcessing') },
      { value: 'success', label: t('common:documents.statusSuccess') },
      { value: 'failed', label: t('common:documents.statusFailed') },
      { value: 'needs_review', label: t('common:documents.statusNeedsReview') },
    ],
    [t],
  )

  const fetchDocuments = async (filterStatus: string) => {
    setLoading(true)
    setError('')
    try {
      const response = await api.get<DataResponse<PaginatedResponse<Document>>>('/documents', {
        params: { status: filterStatus || undefined, page: 1, page_size: 50 },
      })
      setDocuments(response.data.data?.items || [])
    } catch (err) {
      setError(getErrorMessage(err, t('common:documents.loadFailed')))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchDocuments(status)
  }, [status])

  // URL 直连：带 id 时拉单条详情填入 selected，自动打开详情 Modal
  useEffect(() => {
    if (!id) {
      setSelected(null)
      return
    }
    let cancelled = false
    const fetchDetail = async () => {
      try {
        const response = await api.get<DataResponse<Document>>(`/documents/${id}`)
        if (!cancelled) setSelected(response.data.data)
      } catch (err) {
        if (!cancelled) setError(getErrorMessage(err, t('common:documents.loadDetailFailed')))
      }
    }
    void fetchDetail()
    return () => {
      cancelled = true
    }
  }, [id, t])

  const handleUploaded = (doc: Document) => {
    setDocuments((prev) => [doc, ...prev])
    toast.success(t('common:documents.statSuccess'), doc.filename)
  }

  const stats = useMemo(() => {
    const total = documents.length
    const success = documents.filter((d) => d.status === 'success').length
    const needsReview = documents.filter((d) => d.status === 'needs_review').length
    const failed = documents.filter((d) => d.status === 'failed').length
    const processing = documents.filter((d) => d.status === 'processing').length
    return { total, success, needsReview, failed, processing }
  }, [documents])

  const statusDistribution = useMemo(() => {
    const counts: Record<string, number> = {}
    documents.forEach((d) => {
      counts[d.status] = (counts[d.status] || 0) + 1
    })
    return Object.entries(counts)
      .map(([s, count]) => ({ status: s, count }))
      .sort((a, b) => b.count - a.count)
  }, [documents])

  // 关键词过滤（客户端，按文件名匹配）
  const filteredDocuments = useMemo(() => {
    const kw = keyword.trim().toLowerCase()
    if (!kw) return documents
    return documents.filter((d) => (d.filename || '').toLowerCase().includes(kw))
  }, [documents, keyword])

  return (
    <div className="container">
      <div className="page-header">
        <h1>{t('common:documents.title')}</h1>
      </div>

      <div className="stat-grid compact">
        <div className={`stat-card ${!stats.total ? 'is-zero' : ''}`}>
          <div className="stat-card-head">
            <div className="stat-icon documents">
              <ICONS.documents size={20} />
            </div>
          </div>
          <div className="stat-value">{stats.total}</div>
          <div className="stat-label">{t('common:documents.statTotal')}</div>
        </div>
        <div className={`stat-card ${!stats.success ? 'is-zero' : ''}`}>
          <div className="stat-card-head">
            <div className="stat-icon" style={{ background: 'var(--color-success-subtle)', color: 'var(--color-success)' }}>
              <ICONS.check size={20} />
            </div>
          </div>
          <div className="stat-value">{stats.success}</div>
          <div className="stat-label">{t('common:documents.statSuccess')}</div>
        </div>
        <div className={`stat-card ${!stats.needsReview ? 'is-zero' : ''}`}>
          <div className="stat-card-head">
            <div className="stat-icon" style={{ background: 'var(--color-warning-subtle)', color: 'var(--color-warning)' }}>
              <ICONS.approvals size={20} />
            </div>
          </div>
          <div className="stat-value">{stats.needsReview}</div>
          <div className="stat-label">{t('common:documents.statNeedsReview')}</div>
        </div>
        <div className={`stat-card ${!stats.processing ? 'is-zero' : ''}`}>
          <div className="stat-card-head">
            <div className="stat-icon" style={{ background: 'var(--color-primary-subtle)', color: 'var(--color-primary-ink)' }}>
              <ICONS.refresh size={20} />
            </div>
          </div>
          <div className="stat-value">{stats.processing}</div>
          <div className="stat-label">{t('common:documents.statProcessing')}</div>
        </div>
        <div className={`stat-card ${!stats.failed ? 'is-zero' : ''}`}>
          <div className="stat-card-head">
            <div className="stat-icon" style={{ background: 'var(--color-down-subtle)', color: 'var(--color-down)' }}>
              <ICONS.close size={20} />
            </div>
          </div>
          <div className="stat-value">{stats.failed}</div>
          <div className="stat-label">{t('common:documents.statFailed')}</div>
        </div>
      </div>

      {statusDistribution.length > 0 && (
        <div className="card status-summary">
          <h3 className="card-title">{t('common:documents.statusDistribution')}</h3>
          <div className="status-badges">
            {statusDistribution.map((item) => (
              <div key={item.status} className="status-badge-item">
                <Badge status={item.status} />
                <span className="status-count">{item.count}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="toolbar">
        <div className="form-group">
          <label htmlFor="status-filter">{t('common:documents.filterStatus')}</label>
          <select
            id="status-filter"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            {statusOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        {documents.length > 0 && (
          <div className="search-inline">
            <ICONS.search size={14} />
            <input
              type="search"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              placeholder={t('common:documents.searchPlaceholder')}
              aria-label={t('common:documents.searchPlaceholder')}
            />
          </div>
        )}
      </div>

      <DocumentUpload onUploaded={handleUploaded} />

      {error && (
        <div className="alert alert-error mb-4" role="alert">
          <span>{error}</span>
          <button type="button" className="chat-error-retry" onClick={() => fetchDocuments(status)}>
            {t('common:documents.retry')}
          </button>
        </div>
      )}

      {loading ? (
        <Loading text={t('common:documents.loading')} />
      ) : documents.length === 0 ? (
        <EmptyState
          icon="documents"
          title={t('common:documents.emptyTitle')}
          description={t('common:documents.emptyDesc')}
          action={
            <button type="button" className="secondary" onClick={() => fetchDocuments(status)}>
              {t('common:documents.retry')}
            </button>
          }
        />
      ) : filteredDocuments.length === 0 ? (
        <EmptyState
          icon="search"
          title={t('common:documents.emptySearchTitle')}
          description={t('common:documents.emptySearchDesc')}
        />
      ) : (
        <DocumentList documents={filteredDocuments} onSelect={setSelected} />
      )}

      {selected && <DocumentDetail document={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}
