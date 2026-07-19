import type {
  ReportSubscription,
  SubscriptionChannel,
  SubscriptionExportFormat,
  SubscriptionFrequency,
  SubscriptionReportType,
} from '../../types/reportSubscription.ts'

export const REPORT_TYPES: { value: SubscriptionReportType; label: string }[] = [
  { value: 'profit', label: '利润表' },
  { value: 'balance', label: '资产负债表' },
  { value: 'cash', label: '现金流量表' },
  { value: 'custom', label: '自定义' },
]

export const FREQUENCIES: { value: SubscriptionFrequency; label: string }[] = [
  { value: 'daily', label: '每日' },
  { value: 'weekly', label: '每周' },
  { value: 'monthly', label: '每月' },
]

export const EXPORT_FORMATS: { value: SubscriptionExportFormat; label: string }[] = [
  { value: 'pdf', label: 'PDF' },
  { value: 'xlsx', label: 'Excel' },
  { value: 'markdown', label: 'Markdown' },
  { value: 'json', label: 'JSON' },
]

export const CHANNELS: { value: SubscriptionChannel; label: string }[] = [
  { value: 'in_app', label: '站内信' },
  { value: 'email', label: '邮件' },
  { value: 'im', label: 'IM' },
]

export const WEEKDAYS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

export interface FormState {
  name: string
  report_type: SubscriptionReportType
  year: string
  period: string
  frequency: SubscriptionFrequency
  at_hour: string
  at_minute: string
  day_of_week: string
  day_of_month: string
  export_format: SubscriptionExportFormat
  channels: SubscriptionChannel[]
  recipients: string
}

export const emptyForm: FormState = {
  name: '',
  report_type: 'profit',
  year: String(new Date().getFullYear()),
  period: 'Q2',
  frequency: 'daily',
  at_hour: '8',
  at_minute: '0',
  day_of_week: '0',
  day_of_month: '1',
  export_format: 'pdf',
  channels: ['in_app'],
  recipients: '',
}

export function formatFrequency(sub: ReportSubscription): string {
  const time = `${String(sub.at_hour).padStart(2, '0')}:${String(sub.at_minute).padStart(2, '0')}`
  if (sub.frequency === 'weekly') {
    return `每周${WEEKDAYS[sub.day_of_week ?? 0]} ${time}`
  }
  if (sub.frequency === 'monthly') {
    return `每月${sub.day_of_month ?? 1}日 ${time}`
  }
  return `每日 ${time}`
}
