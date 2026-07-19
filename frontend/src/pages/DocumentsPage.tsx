import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../api/client'
import { getErrorMessage } from '../utils/errors'
import type { Document } from '../types/document'
import type { DataResponse, PaginatedResponse } from '../types/report'
import DocumentDetail from '../components/DocumentDetail'
import DocumentList from '../components/DocumentList'
import DocumentUpload from '../components/DocumentUpload'
import Loading from '../components/ui/Loading.tsx'
import Badge from '../components/ui/Badge.tsx'
import { ICONS } from '../components/ui/Icons.tsx'

const statusOptions: { value: string; label: string }[] = [
  { value: '', label: '全部' },
  { value: 'pending', label: '待处理' },
  { value: 'processing', label: '解析中' },
  { value: 'success', label: '成功' },
  { value: 'failed', label: '失败' },
  { value: 'needs_review', label: '待复核' },
]

const STATUS_LABELS: Record<string, string> = {
  pending: '待处理',
  processing: '解析中',
  success: '成功',
  failed: '失败',
  needs_review: '待复核',
}

export default function DocumentsPage() {
  const { id } = useParams<{ id: string }>()
  const [documents, setDocuments] = useState<Document[]>([])
  const [selected, setSelected] = useState<Document | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [status, setStatus] = useState('')

  const fetchDocuments = async (filterStatus: string) => {
    setLoading(true)
    setError('')
    try {
      const response = await api.get<DataResponse<PaginatedResponse<Document>>>('/documents', {
        params: { status: filterStatus || undefined, page: 1, page_size: 50 },
      })
      setDocuments(response.data.data?.items || [])
    } catch (err) {
      setError(getErrorMessage(err, '加载文档列表失败'))
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
        if (!cancelled) setError(getErrorMessage(err, '加载文档详情失败'))
      }
    }
    void fetchDetail()
    return () => {
      cancelled = true
    }
  }, [id])

  const handleUploaded = (doc: Document) => {
    setDocuments((prev) => [doc, ...prev])
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
      .map(([status, count]) => ({ status, label: STATUS_LABELS[status] || status, count }))
      .sort((a, b) => b.count - a.count)
  }, [documents])

  return (
    <div className="container">
      <div className="page-header">
        <h1>文档解析</h1>
      </div>

      <div className="stat-grid compact">
        <div className={`stat-card ${!stats.total ? 'is-zero' : ''}`}>
          <div className="stat-card-head">
            <div className="stat-icon documents">
              <ICONS.documents size={20} />
            </div>
          </div>
          <div className="stat-value">{stats.total}</div>
          <div className="stat-label">全部文档</div>
        </div>
        <div className={`stat-card ${!stats.success ? 'is-zero' : ''}`}>
          <div className="stat-card-head">
            <div className="stat-icon" style={{ background: 'var(--color-success-subtle)', color: 'var(--color-success)' }}>
              <ICONS.check size={20} />
            </div>
          </div>
          <div className="stat-value">{stats.success}</div>
          <div className="stat-label">解析成功</div>
        </div>
        <div className={`stat-card ${!stats.needsReview ? 'is-zero' : ''}`}>
          <div className="stat-card-head">
            <div className="stat-icon" style={{ background: 'var(--color-warning-subtle)', color: 'var(--color-warning)' }}>
              <ICONS.approvals size={20} />
            </div>
          </div>
          <div className="stat-value">{stats.needsReview}</div>
          <div className="stat-label">待复核</div>
        </div>
        <div className={`stat-card ${!stats.processing ? 'is-zero' : ''}`}>
          <div className="stat-card-head">
            <div className="stat-icon" style={{ background: 'var(--color-primary-subtle)', color: 'var(--color-primary-ink)' }}>
              <ICONS.refresh size={20} />
            </div>
          </div>
          <div className="stat-value">{stats.processing}</div>
          <div className="stat-label">解析中</div>
        </div>
        <div className={`stat-card ${!stats.failed ? 'is-zero' : ''}`}>
          <div className="stat-card-head">
            <div className="stat-icon" style={{ background: 'var(--color-down-subtle)', color: 'var(--color-down)' }}>
              <ICONS.close size={20} />
            </div>
          </div>
          <div className="stat-value">{stats.failed}</div>
          <div className="stat-label">失败</div>
        </div>
      </div>

      {statusDistribution.length > 0 && (
        <div className="card status-summary">
          <h3 className="card-title">状态分布</h3>
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
          <label htmlFor="status-filter">状态筛选</label>
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
      </div>

      <DocumentUpload onUploaded={handleUploaded} />

      {error && (
        <div className="alert alert-error mb-4" role="alert">
          {error}
        </div>
      )}

      {loading ? <Loading text="加载文档中..." /> : <DocumentList documents={documents} onSelect={setSelected} />}

      {selected && <DocumentDetail document={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}
