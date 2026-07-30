import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { api } from '../../api/client'
import { getErrorMessage } from '../../utils/errors'
import type { Report, DataResponse } from '../../types/report'
import { ICONS } from '../../components/ui/Icons'
import Badge from '../../components/ui/Badge'
import { CHART_COLORS } from '../../components/charts/chartTokens'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import MobilePageHeader from '../../components/mobile/MobilePageHeader'
import '../../i18n/mobile'

const STATUS_KEY: Record<string, string> = {
  draft: 'common:reports.statusDraft',
  pending: 'common:reports.statusPending',
  processing: 'common:reports.statusProcessing',
  reviewing: 'common:reports.statusReviewing',
  approved: 'common:reports.statusApproved',
  rejected: 'common:reports.statusRejected',
  failed: 'common:reports.statusFailed',
}

const EXPORT_FORMATS: Array<{ value: 'pdf' | 'xlsx' | 'markdown' | 'json'; label: string }> = [
  { value: 'pdf', label: 'PDF' },
  { value: 'xlsx', label: 'Excel' },
  { value: 'markdown', label: 'Markdown' },
  { value: 'json', label: 'JSON' },
]

/**
 * 移动端报告详情：整页单列视图，顶部返回 + 状态 + 摘要 + 指标列表 + 导出。
 * 与桌面 Modal 详情不同，移动端把长内容铺开为可滚动页面，操作按钮触手可及。
 */
export default function ReportDetailMobile({ id }: { id: string }) {
  const { t } = useTranslation(['common', 'mobile'])
  const navigate = useNavigate()
  const [report, setReport] = useState<Report | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState('')

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError('')
    void api
      .get<DataResponse<Report>>(`/reports/${id}`)
      .then((res) => {
        if (!cancelled) setReport(res.data.data)
      })
      .catch((err) => {
        if (!cancelled) setError(getErrorMessage(err, t('common:reports.loadDetailFailed')))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [id, t])

  const chartData = useMemo(() => {
    if (!report?.content) return []
    return report.content.sections
      .filter((s) => typeof s.value === 'number')
      .map((s) => ({ name: s.name, value: s.value as number }))
  }, [report])

  const canExport = report
    ? report.status === 'reviewing' || report.status === 'approved'
    : false

  const handleExport = async (format: 'pdf' | 'xlsx' | 'markdown' | 'json') => {
    if (!report) return
    setExporting(true)
    setExportError('')
    try {
      const response = await api.post(`/reports/${report.id}/export`, {}, { params: { format } })
      const url = response.data.data?.content_url
      if (!url) {
        setExportError('导出链接获取失败')
        return
      }
      window.open(url, '_blank', 'noopener,noreferrer')
    } catch (err) {
      setExportError(getErrorMessage(err, '导出失败'))
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className="mdetail">
      <MobilePageHeader
        title={report?.title || t('common:reports.title')}
        onBack={() => navigate('/reports')}
      />

      {loading ? (
        <div className="mdetail__loading">{t('common:status.loading')}</div>
      ) : error ? (
        <div className="mdetail__error" role="alert">
          <span>{error}</span>
        </div>
      ) : report ? (
        <div className="mdetail__body">
          <div className="mdetail__row">
            <span className="mdetail__label">{t('common:reports.colStatus')}</span>
            <Badge
              status={report.status}
              label={t(STATUS_KEY[report.status] || 'common:reports.statusDraft')}
            />
          </div>

          {report.summary && (
            <div className="mdetail__block">
              <span className="mdetail__label">摘要</span>
              <p className="mdetail__summary">{report.summary}</p>
            </div>
          )}

          {report.content && (
            <div className="mdetail__block">
              <span className="mdetail__label">{report.content.title}</span>
              {chartData.length > 0 && (
                <div className="mdetail__chart">
                  <ResponsiveContainer width="100%" height={200}>
                    <BarChart data={chartData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                      <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                      <YAxis tick={{ fontSize: 11 }} />
                      <Tooltip />
                      <Bar dataKey="value" fill={CHART_COLORS[0]} radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
              <ul className="mdetail__metrics">
                {report.content.sections.map((s, i) => (
                  <li key={i} className="mdetail__metric">
                    <span className="mdetail__metric-name">{s.name}</span>
                    <span className="mdetail__metric-value">
                      {typeof s.value === 'number' ? s.value.toLocaleString() : String(s.value)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {exportError && (
            <div className="mdetail__alert" role="alert">
              {exportError}
            </div>
          )}

          {canExport ? (
            <div className="mdetail__export">
              <span className="mdetail__label">导出</span>
              <div className="mdetail__export-row">
                {EXPORT_FORMATS.map((f) => (
                  <button
                    key={f.value}
                    type="button"
                    className="mdetail__export-btn"
                    disabled={exporting}
                    onClick={() => void handleExport(f.value)}
                  >
                    <ICONS.download size={16} />
                    {f.label}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="mdetail__hint">{t('common:reports.statusReviewing')} / {t('common:reports.statusApproved')} 后可导出</div>
          )}
        </div>
      ) : null}
    </div>
  )
}
