import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client.ts'
import { getErrorMessage } from '../utils/errors.ts'
import type { Report, DataResponse, PaginatedResponse } from '../types/report.ts'
import ReportList from '../components/ReportList.tsx'
import ReportDetail from '../components/ReportDetail.tsx'
import ReportCreate from '../components/ReportCreate.tsx'
import Loading from '../components/ui/Loading.tsx'
import Badge from '../components/ui/Badge.tsx'

const STATUS_LABELS: Record<string, string> = {
  draft: '草稿',
  pending: '待处理',
  processing: '生成中',
  reviewing: '待复核',
  approved: '已通过',
  rejected: '已驳回',
}

export default function ReportsPage() {
  const { id } = useParams<{ id: string }>()
  const [selected, setSelected] = useState<Report | null>(null)
  const queryClient = useQueryClient()

  // 报告列表
  const {
    data: reports = [],
    isLoading: loading,
    error: listError,
  } = useQuery<Report[]>({
    queryKey: ['reports'],
    queryFn: async () => {
      const response = await api.get<DataResponse<PaginatedResponse<Report>>>('/reports', {
        params: { page: 1, page_size: 50 },
      })
      return response.data.data?.items || []
    },
  })

  const error = listError ? getErrorMessage(listError, '加载报告列表失败') : ''

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
      .map(([status, count]) => ({ status, label: STATUS_LABELS[status] || status, count }))
      .sort((a, b) => b.count - a.count)
  }, [reports])

  return (
    <div className="container">
      <div className="page-header">
        <h1>财务报告</h1>
      </div>

      <div className="stat-grid compact">
        <div className="stat-card">
          <div className="stat-value">{stats.total}</div>
          <div className="stat-label">全部报告</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{stats.approved}</div>
          <div className="stat-label">已通过</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{stats.reviewing}</div>
          <div className="stat-label">待复核</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{stats.failed}</div>
          <div className="stat-label">生成失败</div>
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

      <ReportCreate onCreated={handleCreated} />

      {error && (
        <div className="alert alert-error mb-4" role="alert">
          {error}
        </div>
      )}

      {loading ? <Loading text="加载报告中..." /> : <ReportList reports={reports} onSelect={setSelected} />}

      {selected && <ReportDetail report={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}
