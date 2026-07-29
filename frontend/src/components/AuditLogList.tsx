import { useTranslation } from 'react-i18next'
import EmptyState from './ui/EmptyState.tsx'
import type { AuditLog } from '../types/audit'
import { formatDateTime } from '../utils/format.ts'

interface AuditLogListProps {
  logs: AuditLog[]
}

export default function AuditLogList({ logs }: AuditLogListProps) {
  const { t } = useTranslation()
  if (logs.length === 0) {
    return (
      <EmptyState
        icon="audit"
        title={t('common:audit.emptyTitle')}
        description={t('common:audit.emptyDesc')}
      />
    )
  }

  return (
    <div className="table-wrapper">
      <table>
        <thead>
          <tr>
            <th>{t('common:audit.colTime')}</th>
            <th>{t('common:audit.colAction')}</th>
            <th>{t('common:audit.colResource')}</th>
            <th>{t('common:audit.colResult')}</th>
            <th>{t('common:audit.colIp')}</th>
            <th>{t('common:audit.colReason')}</th>
          </tr>
        </thead>
        <tbody>
          {logs.map((log) => (
            <tr key={log.id}>
              <td>{formatDateTime(log.timestamp)}</td>
              <td>{log.action}</td>
              <td>{log.resource}</td>
              <td>{log.result || '-'}</td>
              <td>{log.ip || '-'}</td>
              <td>{log.reason || '-'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
