import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client.ts'
import { getErrorMessage } from '../utils/errors.ts'
import type { Report, DataResponse, PaginatedResponse } from '../types/report.ts'
import ReportList from '../components/ReportList.tsx'
import ReportDetail from '../components/ReportDetail.tsx'
import ReportCreate from '../components/ReportCreate.tsx'
import Loading from '../components/ui/Loading.tsx'
import EmptyState from '../components/ui/EmptyState.tsx'
import Badge from '../components/ui/Badge.tsx'
import { ICONS } from '../components/ui/Icons.tsx'
import { toast } from '../components/ui/Toaster.tsx'
import { useDevice } from '../context/DeviceContext'
import ReportsMobile from './mobile/ReportsMobile'
import ReportDetailMobile from './mobile/ReportDetailMobile'

/** 处于生成中的状态，需要自动轮询刷新 */
const GENERATING_STATUSES = new Set(['processing', 'pending'])

export default function ReportsPage() {
  const { t } = useTranslation()
  const { id } = useParams<{ id: string }>()
  const { isMobile } = useDevice()
  if (isMobile) return id ? <ReportDetailMobile id={id} /> : <ReportsMobile />
  const [selected, setSelected] = useState<Report | null>(null)
  const [status, setStatus] = useState('')
  const [keyword, setKeyword] = useState('')
  const queryClient = useQueryClient()

  const statusOptions = useMemo(
    () => [
      { value: '', label: t('common:reports.statusAll') },
      { value: 'draft', label: t('common:reports.statusDraft') },
      { value: 'pending', label: t('common:reports.statusPending') },
      { value: 'processing', label: t('common:reports.statusProcessing') },
      { value: 'reviewing', label: t('common:reports.statusReviewing') },
      { value: 'approved', label: t('common:reports.statusApproved') },
      { value: 'rejected', label: t('common:reports.statusRejected') },
      { value: 'failed', label: t('common:reports.statusFailed') },
    ],
    [t],
  )

  // 报告列表
  const {
    data: reports = [],
    isLoading: loading,
    error: listError,
    refetch,
  } = useQuery<Report[]>({
    queryKey: ['reports'],
    queryFn: async () => {
      const response = await api.get<DataResponse<PaginatedResponse<Report>>>('/reports', {
        params: { page: 1, page_size: 50 },
      })
      return response.data.data?.items || []
    },
    // 有报告生成中时自动轮询，每 5 秒刷新一次
    refetchInterval: (query) => {
      const data = query.state.data as Report[] | undefined
      if (data && data.some((r) => GENERATING_STATUSES.has(r.status))) {
        return 5000
      }
      return false
    },
  })

  const error = listError ? getErrorMessage(listError, t('common:reports.loadFailed')) : ''
  const hasGenerating = reports.some((r) => GENERATING_STATUSES.has(r.status))

  // URL 直连：带 id 时拉单条详情填入 selected，自动打开详情 Modal
  const { data: detailData } = useQuery<Report | null>({
    queryKey: ['report-detail', id],
    queryFn: async () => {
      const response = await api.get<DataResponse<Report>>(`/reports/${id}`)
      return response.data.data ?? null
    },
    enabled: !!id,
  })

  useEffect(() => {
    if (id && detailData !== undefined) setSelected(detailData)
  }, [id, detailData])

  const handleCreated = () => {
    queryClient.invalidateQueries({ queryKey: ['reports'] })
    toast.success(t('common:reports.title'), t('common:reports.statusProcessing'))
  }

  const stats = useMemo(() => {
    const total = reports.length
    const approved = reports.filter((r) => r.status === 'approved').length
    const reviewing = reports.filter((r) => r.status === 'reviewing').length
    const failed = reports.filter((r) => r.status === 'failed').length
    return { total, approved, reviewing, failed }
  }, [reports])

  const statusDistribution = useMemo(() => {
    const counts: Record<string, number> = {}
    reports.forEach((r) => {
      counts[r.status] = (counts[r.status] || 0) + 1
    })
    return Object.entries(counts)
      .map(([s, count]) => ({ status: s, count }))
      .sort((a, b) => b.count - a.count)
  }, [reports])

  // 状态 + 关键词过滤（客户端）
  const filteredReports = useMemo(() => {
    let list = reports
    if (status) {
      list = list.filter((r) => r.status === status)
    }
    const kw = keyword.trim().toLowerCase()
    if (kw) {
      list = list.filter((r) => (r.title || '').toLowerCase().includes(kw))
    }
    return list
  }, [reports, status, keyword])

  return (
    <div className="container">
      <div className="page-header">
        <h1>{t('common:reports.title')}</h1>
        {hasGenerating && (
          <span className="badge processing generating-hint">
            <ICONS.refresh size={12} />
            {t('common:reports.refreshingHint')}
          </span>
        )}
      </div>

      <div className="stat-grid compact">
        <div className="stat-card">
          <div className="stat-value">{stats.total}</div>
          <div className="stat-label">{t('common:reports.statTotal')}</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{stats.approved}</div>
          <div className="stat-label">{t('common:reports.statApproved')}</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{stats.reviewing}</div>
          <div className="stat-label">{t('common:reports.statReviewing')}</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{stats.failed}</div>
          <div className="stat-label">{t('common:reports.statFailed')}</div>
        </div>
      </div>

      {statusDistribution.length > 0 && (
        <div className="card status-summary">
          <h3 className="card-title">{t('common:reports.statusDistribution')}</h3>
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

      <ReportCreate onCreated={handleCreated} />

      <div className="toolbar">
        <div className="form-group">
          <label htmlFor="status-filter">{t('common:reports.filterStatus')}</label>
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
        {reports.length > 0 && (
          <div className="search-inline">
            <ICONS.search size={14} />
            <input
              type="search"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              placeholder={t('common:reports.searchPlaceholder')}
              aria-label={t('common:reports.searchPlaceholder')}
            />
          </div>
        )}
      </div>

      {error && (
        <div className="alert alert-error mb-4" role="alert">
          <span>{error}</span>
          <button type="button" className="chat-error-retry" onClick={() => refetch()}>
            {t('common:reports.retry')}
          </button>
        </div>
      )}

      {loading ? (
        <Loading text={t('common:reports.loading')} />
      ) : reports.length === 0 ? (
        <EmptyState
          icon="reports"
          title={t('common:reports.emptyTitle')}
          description={t('common:reports.emptyDesc')}
          action={
            <button type="button" className="secondary" onClick={() => refetch()}>
              {t('common:reports.retry')}
            </button>
          }
        />
      ) : filteredReports.length === 0 ? (
        <EmptyState
          icon="search"
          title={t('common:reports.emptySearchTitle')}
          description={t('common:reports.emptySearchDesc')}
        />
      ) : (
        <ReportList reports={filteredReports} onSelect={setSelected} />
      )}

      {selected && <ReportDetail report={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}
