import { useTranslation } from 'react-i18next'
import Badge from './ui/Badge.tsx'
import EmptyState from './ui/EmptyState.tsx'
import type { Report } from '../types/report.ts'
import { formatDateTime } from '../utils/format.ts'

interface ReportListProps {
  reports: Report[]
  onSelect: (report: Report) => void
}

export default function ReportList({ reports, onSelect }: ReportListProps) {
  const { t } = useTranslation()
  if (reports.length === 0) {
    return (
      <EmptyState
        icon="reports"
        title={t('common:reports.emptyTitle')}
        description={t('common:reports.emptyDesc')}
      />
    )
  }

  return (
    <div className="table-wrapper">
      <table className="financial">
        <thead>
          <tr>
            <th>{t('common:reports.colTitle')}</th>
            <th>{t('common:reports.colType')}</th>
            <th>{t('common:reports.colStatus')}</th>
            <th>{t('common:reports.colCreatedAt')}</th>
            <th>{t('common:reports.colActions')}</th>
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
                  {t('common:reports.view')}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
