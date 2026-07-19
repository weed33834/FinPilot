export interface DashboardSummary {
  greeting: string
  report_count: number
  pending_approval_count: number
  document_count: number
  recent_reports: Array<{
    id: string
    title: string
    status: string
    created_at: string
  }>
  recent_documents: Array<{
    id: string
    filename: string
    status: string
    created_at: string
  }>
  report_status_distribution: Record<string, number>
  document_status_distribution: Record<string, number>
  recent_activities: Array<{
    id: string
    action: string
    resource: string
    result: string
    created_at: string
  }>
  approval_trend: Array<{
    date: string
    count: number
  }>
  // Extended fields for financial dashboard
  processing_query_count?: number
  approved_report_count?: number
  total_approval_count?: number
  parsed_document_count?: number
  today_query_count?: number
}

export const REPORT_STATUS_COLORS: Record<string, string> = {
  draft: 'var(--color-text-muted)',
  pending: 'var(--color-warning)',
  processing: 'var(--color-info)',
  reviewing: 'var(--color-purple)',
  approved: 'var(--color-success)',
  rejected: 'var(--color-danger)',
  published: 'var(--color-primary)',
  failed: 'var(--color-danger)',
}

export const DOCUMENT_STATUS_COLORS: Record<string, string> = {
  pending: 'var(--color-warning)',
  processing: 'var(--color-info)',
  success: 'var(--color-success)',
  needs_review: 'var(--color-purple)',
  failed: 'var(--color-danger)',
}

export const STATUS_LABELS: Record<string, string> = {
  draft: 'dashboard:status.draft',
  pending: 'dashboard:status.pending',
  processing: 'dashboard:status.processing',
  reviewing: 'dashboard:status.reviewing',
  approved: 'dashboard:status.approved',
  rejected: 'dashboard:status.rejected',
  published: 'dashboard:status.published',
  failed: 'dashboard:status.failed',
  success: 'dashboard:status.success',
  needs_review: 'dashboard:status.needs_review',
  started: 'dashboard:status.processing',
  parsed: 'dashboard:status.parsed',
  uploaded: 'dashboard:status.uploaded',
  completed: 'dashboard:status.completed',
}

// 操作码到 i18n key 的映射，渲染时由组件调用 t() 翻译
export const ACTION_LABELS: Record<string, string> = {
  'report.create': 'dashboard:actions.report.create',
  'report.generate': 'dashboard:actions.report.generate',
  'report.generate.failed': 'dashboard:actions.report.generate.failed',
  'report.export': 'dashboard:actions.report.export',
  'report.approve': 'dashboard:actions.report.approve',
  'report.reject': 'dashboard:actions.report.reject',
  'report.approval.approve': 'dashboard:actions.report.approval.approve',
  'report.approval.reject': 'dashboard:actions.report.approval.reject',
  'report.approval.modify': 'dashboard:actions.report.approval.modify',
  'document.upload': 'dashboard:actions.document.upload',
  'document.create': 'dashboard:actions.document.create',
  'document.parse': 'dashboard:actions.document.parse',
  'document.parse.success': 'dashboard:actions.document.parse.success',
  'document.parse.fail': 'dashboard:actions.document.parse.fail',
  'document.parse.failed': 'dashboard:actions.document.parse.fail',
  'query.nl2sql': 'dashboard:actions.query.nl2sql',
  'queries.nl2sql': 'dashboard:actions.query.nl2sql',
  'agent.chat': 'dashboard:actions.agent.query',
  'agent.query': 'dashboard:actions.agent.query',
  'user.login': 'dashboard:actions.user.login',
  'user.logout': 'dashboard:actions.user.logout',
  'login.success': 'dashboard:actions.login.success',
  'login.failed': 'dashboard:actions.login.failed',
  'api_key.create': 'dashboard:actions.api_key.create',
  'api_key.revoke': 'dashboard:actions.api_key.revoke',
  'api_key.delete': 'dashboard:actions.api_key.delete',
  'api_key.rotate': 'dashboard:actions.api_key.rotate',
}

export const ROLE_TIP_KEYS: Record<string, string> = {
  admin: 'dashboard:tips.admin',
  finance_manager: 'dashboard:tips.finance_manager',
  auditor: 'dashboard:tips.auditor',
  viewer: 'dashboard:tips.viewer',
}

export const SUGGESTION_KEYS = [
  'dashboard:suggestions.s1',
  'dashboard:suggestions.s2',
  'dashboard:suggestions.s3',
  'dashboard:suggestions.s4',
]
