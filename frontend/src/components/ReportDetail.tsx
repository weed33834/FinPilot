import { useState, useMemo } from 'react'
import { api } from '../api/client.ts'
import { getErrorMessage } from '../utils/errors.ts'
import type { Report } from '../types/report.ts'
import Modal from './ui/Modal.tsx'
import Badge from './ui/Badge.tsx'
import { CHART_COLORS } from './charts/chartTokens.ts'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'

interface ReportDetailProps {
  report: Report
  onClose: () => void
}

export default function ReportDetail({ report, onClose }: ReportDetailProps) {
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState('')
  const [format, setFormat] = useState<'pdf' | 'xlsx' | 'markdown' | 'json'>('markdown')

  const canExport = useMemo(
    () => report.status === 'reviewing' || report.status === 'approved',
    [report.status]
  )

  const chartData = useMemo(() => {
    if (!report.content) return []
    return report.content.sections
      .filter((section) => typeof section.value === 'number')
      .map((section) => ({
        name: section.name,
        value: section.value as number,
      }))
  }, [report.content])

  const comparisonChartData = useMemo(() => {
    const chart = report.content?.chart
    if (!chart || chart.series.length === 0) return null
    const labels = chart.series[0].data.map((p) => p.label)
    return {
      labels,
      series: chart.series,
    }
  }, [report.content])

  const handleExport = async () => {
    setExporting(true)
    setExportError('')
    try {
      const response = await api.post(`/reports/${report.id}/export`, {}, {
        params: { format },
      })
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
    <Modal
      title={report.title}
      onClose={onClose}
      footer={
        <>
          <select
            value={format}
            onChange={(e) => setFormat(e.target.value as 'pdf' | 'xlsx' | 'markdown' | 'json')}
          >
            <option value="pdf">PDF</option>
            <option value="xlsx">Excel</option>
            <option value="markdown">Markdown</option>
            <option value="json">JSON</option>
          </select>
          <button
            type="button"
            onClick={handleExport}
            disabled={exporting || !canExport}
            title={canExport ? '导出报告' : '仅 reviewing 或 approved 状态的报告可导出'}
          >
            {exporting ? '导出中...' : '导出'}
          </button>
          {report.content_url && (
            <a href={report.content_url} target="_blank" rel="noreferrer noopener" className="link">
              已导出文件
            </a>
          )}
          <button type="button" className="secondary" onClick={onClose}>
            关闭
          </button>
        </>
      }
    >
      <div className="detail-grid">
        <div>
          <span className="text-muted text-sm">状态</span>
          <div>
            <Badge status={report.status} />
            <span className="text-muted text-sm ml-3">
              类型: {report.report_type}
            </span>
          </div>
        </div>

        {report.error_message && (
          <div className="alert alert-error" role="alert">生成错误: {report.error_message}</div>
        )}

        {report.summary && (
          <div>
            <span className="text-muted text-sm">摘要</span>
            <p>{report.summary}</p>
          </div>
        )}

        {report.content && (
          <div>
            <span className="text-muted text-sm">指标</span>
            <div className="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th>指标</th>
                    <th>数值</th>
                  </tr>
                </thead>
                <tbody>
                  {report.content.sections.map((section) => (
                    <tr key={section.metric}>
                      <td>{section.name}</td>
                      <td>
                        {typeof section.value === 'number'
                          ? section.value.toLocaleString()
                          : section.value ?? '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {comparisonChartData && (
              <div className="modal-chart">
                <div className="text-muted text-sm mb-2">{report.content.chart?.title}</div>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={comparisonChartData.labels.map((label) => {
                      const row: Record<string, string | number> = { label }
                      comparisonChartData.series.forEach((s) => {
                        const point = s.data.find((p) => p.label === label)
                        row[s.name] = point ? point.value : 0
                      })
                      return row
                    })}
                    margin={{ top: 8, right: 16, left: 0, bottom: 0 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border-light)" />
                    <XAxis dataKey="label" tick={{ fontSize: 12, fill: 'var(--color-text-secondary)' }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fontSize: 12, fill: 'var(--color-text-secondary)' }} axisLine={false} tickLine={false} />
                    <Tooltip
                      contentStyle={{
                        background: 'var(--color-surface)',
                        border: '1px solid var(--color-border)',
                        borderRadius: 'var(--radius-md)',
                        fontSize: 'var(--text-sm)',
                      }}
                      cursor={{ fill: 'var(--color-primary-subtle)' }}
                    />
                    {comparisonChartData.series.map((s, idx) => (
                      <Bar
                        key={s.metric}
                        dataKey={s.name}
                        fill={CHART_COLORS[idx % CHART_COLORS.length]}
                        radius={[4, 4, 0, 0]}
                      />
                    ))}
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
            {!comparisonChartData && chartData.length > 0 && (
              <div className="modal-chart">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="name" />
                    <YAxis />
                    <Tooltip />
                    <Bar dataKey="value" fill="var(--color-primary)" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>
        )}

        {exportError && (
          <div className="alert alert-error" role="alert">
            {exportError}
          </div>
        )}
      </div>
    </Modal>
  )
}
