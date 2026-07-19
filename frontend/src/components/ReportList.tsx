import Badge from './ui/Badge.tsx'
import EmptyState from './ui/EmptyState.tsx'
import type { Report } from '../types/report.ts'
import { formatDateTime } from '../utils/format.ts'

interface ReportListProps {
  reports: Report[]
  onSelect: (report: Report) => void
}

export default function ReportList({ reports, onSelect }: ReportListProps) {
  if (reports.length === 0) {
    return <EmptyState title="暂无报告" description="创建报告后，它们会出现在这里。" />
  }

  return (
    <div className="table-wrapper">
      <table className="financial">
        <thead>
          <tr>
            <th>标题</th>
            <th>类型</th>
            <th>状态</th>
            <th>创建时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {reports.map((report) => (
            <tr key={report.id}>
              <td>{report.title}</td>
              <td>{report.report_type}</td>
              <td>
                <Badge status={report.status} />
              </td>
              <td>{formatDateTime(report.created_at)}</td>
              <td>
                <button type="button" className="secondary" onClick={() => onSelect(report)}>
                  查看
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
