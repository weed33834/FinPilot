import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import Badge from '../../components/ui/Badge.tsx'
import { ICONS } from '../../components/ui/Icons.tsx'
import { formatDateTime } from '../../utils/format.ts'
import { ACTION_LABELS, type DashboardSummary } from './constants.ts'

interface RecentReportsListProps {
  items: DashboardSummary['recent_reports']
}

export function RecentReportsList({ items }: RecentReportsListProps) {
  const { t } = useTranslation(['common', 'dashboard'])
  return (
    <div className="card">
      <div className="dashboard-card-head">
        <h3 className="card-title">{t('dashboard:sections.recentReports')}</h3>
        <Link to="/reports" className="card-link">{t('common:actions.viewAll') || '查看全部'}</Link>
      </div>
      {items.length === 0 ? (
        <div className="empty-state empty-state-sm">
          <ICONS.reports size={32} className="empty-state-icon" />
          <p className="empty-state-title">{t('dashboard:empty.recentReports')}</p>
          <p className="empty-state-desc">{t('dashboard:empty.recentReportsDesc') || '点击下方按钮生成第一份报告'}</p>
          <Link to="/agent" className="btn btn-sm mt-3">{t('dashboard:actions.createReport') || '创建报告'}</Link>
        </div>
      ) : (
        <ul className="activity-list">
          {items.slice(0, 6).map((report) => (
            <li key={report.id}>
              <div className="activity-main">
                <Link to={`/reports/${report.id}`} className="link">
                  {report.title}
                </Link>
                <Badge status={report.status} />
              </div>
              <div className="activity-time">{formatDateTime(report.created_at)}</div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

interface RecentDocumentsListProps {
  items: DashboardSummary['recent_documents']
}

export function RecentDocumentsList({ items }: RecentDocumentsListProps) {
  const { t } = useTranslation(['common', 'dashboard'])
  return (
    <div className="card">
      <div className="dashboard-card-head">
        <h3 className="card-title">{t('dashboard:sections.recentDocuments')}</h3>
        <Link to="/documents" className="card-link">{t('common:actions.viewAll') || '查看全部'}</Link>
      </div>
      {items.length === 0 ? (
        <div className="empty-state empty-state-sm">
          <ICONS.documents size={32} className="empty-state-icon" />
          <p className="empty-state-title">{t('dashboard:empty.recentDocuments')}</p>
          <p className="empty-state-desc">{t('dashboard:empty.recentDocumentsDesc') || '上传 PDF / Excel 让系统自动解析关键数据'}</p>
          <Link to="/documents" className="btn btn-sm mt-3">{t('dashboard:actions.uploadDoc') || '上传文档'}</Link>
        </div>
      ) : (
        <ul className="activity-list">
          {items.slice(0, 6).map((doc) => (
            <li key={doc.id}>
              <div className="activity-main">
                <Link to={`/documents/${doc.id}`} className="link">
                  {doc.filename}
                </Link>
                <Badge status={doc.status} />
              </div>
              <div className="activity-time">{formatDateTime(doc.created_at)}</div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

interface RecentActivitiesListProps {
  items: DashboardSummary['recent_activities']
}

/** 将原始资源标识符转换为用户可读的标签 */
function formatResourceLabel(resource: string): string {
  if (!resource || resource === '-') return '—'
  // user://uuid → 用户
  if (resource.startsWith('user://')) return '用户'
  // api_key:uuid → API 密钥
  if (resource.startsWith('api_key:')) return 'API 密钥'
  // report:uuid → 报告
  if (resource.startsWith('report://') || resource.startsWith('report:')) return '报告'
  // document:uuid → 文档
  if (resource.startsWith('document://') || resource.startsWith('document:')) return '文档'
  // query:uuid → 查询
  if (resource.startsWith('query://') || resource.startsWith('query:')) return '查询'
  // 截断过长的 UUID
  if (resource.length > 40) return resource.slice(0, 36) + '…'
  return resource
}

export function RecentActivitiesList({ items }: RecentActivitiesListProps) {
  const { t } = useTranslation(['common', 'dashboard'])
  return (
    <div className="card">
      <div className="dashboard-card-head">
        <h3 className="card-title">{t('dashboard:sections.recentActivities')}</h3>
        <span className="card-meta">{t('dashboard:meta.recent7d') || '近 7 天'}</span>
      </div>
      {items.length === 0 ? (
        <div className="empty-state empty-state-sm">
          <ICONS.audit size={32} className="empty-state-icon" />
          <p className="empty-state-title">{t('dashboard:empty.recentActivities')}</p>
          <p className="empty-state-desc">{t('dashboard:empty.recentActivitiesDesc') || '系统操作将自动记录在此'}</p>
        </div>
      ) : (
        <ul className="activity-list">
          {items.slice(0, 8).map((activity) => {
            const actionKey = ACTION_LABELS[activity.action]
            const resourceLabel = formatResourceLabel(activity.resource)
            return (
              <li key={activity.id}>
                <div className="activity-main">
                  <span className="activity-title">
                    {actionKey ? t(actionKey) : activity.action}
                  </span>
                  <Badge status={activity.result === 'success' ? 'approved' : 'failed'} />
                </div>
                <div className="activity-resource">{resourceLabel}</div>
                <div className="activity-time">{formatDateTime(activity.created_at)}</div>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
