import EmptyState from './ui/EmptyState.tsx'
import type { AuditLog } from '../types/audit'
import { formatDateTime } from '../utils/format.ts'

interface AuditLogListProps {
  logs: AuditLog[]
}

export default function AuditLogList({ logs }: AuditLogListProps) {
  if (logs.length === 0) {
    return <EmptyState title="暂无审计日志" description="系统操作记录将显示在这里。" />
  }

  return (
    <div className="table-wrapper">
      <table>
        <thead>
          <tr>
            <th>时间</th>
            <th>操作</th>
            <th>资源</th>
            <th>结果</th>
            <th>IP</th>
            <th>原因</th>
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
