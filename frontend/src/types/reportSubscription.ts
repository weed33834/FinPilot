// 报告订阅：定时生成报告、导出并推送通知

export type SubscriptionFrequency = 'daily' | 'weekly' | 'monthly'
export type SubscriptionExportFormat = 'pdf' | 'xlsx' | 'markdown' | 'json'
export type SubscriptionChannel = 'in_app' | 'email' | 'im'
export type SubscriptionReportType = 'profit' | 'balance' | 'cash' | 'custom'

export interface ReportSubscription {
  id: string
  tenant_id: string
  created_by: string | null
  name: string
  report_type: string
  parameters: Record<string, unknown>
  frequency: string
  at_hour: number
  at_minute: number
  day_of_week: number | null
  day_of_month: number | null
  export_format: string
  channels: string[]
  recipients: string[]
  is_active: string
  last_run_at: string | null
  next_run_at: string | null
  last_report_id: string | null
  last_error: string | null
  created_at: string | null
  updated_at: string | null
}

export interface ReportSubscriptionCreate {
  name: string
  report_type: SubscriptionReportType
  parameters: Record<string, unknown>
  frequency: SubscriptionFrequency
  at_hour: number
  at_minute: number
  day_of_week?: number | null
  day_of_month?: number | null
  export_format: SubscriptionExportFormat
  channels: SubscriptionChannel[]
  recipients: string[]
}

export interface ReportSubscriptionUpdate {
  name?: string
  parameters?: Record<string, unknown>
  frequency?: SubscriptionFrequency
  at_hour?: number
  at_minute?: number
  day_of_week?: number | null
  day_of_month?: number | null
  export_format?: SubscriptionExportFormat
  channels?: SubscriptionChannel[]
  recipients?: string[]
  is_active?: 'Y' | 'N'
}

export interface ReportSubscriptionRunResponse {
  subscription_id: string
  report_id: string | null
  status: 'success' | 'failed'
  error: string | null
}
