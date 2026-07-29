import type { TFunction } from 'i18next'
import type {
  ReportSubscription,
  SubscriptionChannel,
  SubscriptionExportFormat,
  SubscriptionFrequency,
  SubscriptionReportType,
} from '../../types/reportSubscription.ts'

export const REPORT_TYPES: { value: SubscriptionReportType; labelKey: string }[] = [
  { value: 'profit', labelKey: 'reportSubscriptions.typeProfit' },
  { value: 'balance', labelKey: 'reportSubscriptions.typeBalance' },
  { value: 'cash', labelKey: 'reportSubscriptions.typeCash' },
  { value: 'custom', labelKey: 'reportSubscriptions.typeCustom' },
]

export const FREQUENCIES: { value: SubscriptionFrequency; labelKey: string }[] = [
  { value: 'daily', labelKey: 'reportSubscriptions.freqDaily' },
  { value: 'weekly', labelKey: 'reportSubscriptions.freqWeekly' },
  { value: 'monthly', labelKey: 'reportSubscriptions.freqMonthly' },
]

export const EXPORT_FORMATS: { value: SubscriptionExportFormat; labelKey: string }[] = [
  { value: 'pdf', labelKey: 'reportSubscriptions.formatPdf' },
  { value: 'xlsx', labelKey: 'reportSubscriptions.formatXlsx' },
  { value: 'markdown', labelKey: 'reportSubscriptions.formatMarkdown' },
  { value: 'json', labelKey: 'reportSubscriptions.formatJson' },
]

export const CHANNELS: { value: SubscriptionChannel; labelKey: string }[] = [
  { value: 'in_app', labelKey: 'reportSubscriptions.channelInApp' },
  { value: 'email', labelKey: 'reportSubscriptions.channelEmail' },
  { value: 'im', labelKey: 'reportSubscriptions.channelIm' },
]

// 周几 i18n key 数组（索引 0 = 周一）
export const WEEKDAYS: string[] = [
  'reportSubscriptions.weekdayMon',
  'reportSubscriptions.weekdayTue',
  'reportSubscriptions.weekdayWed',
  'reportSubscriptions.weekdayThu',
  'reportSubscriptions.weekdayFri',
  'reportSubscriptions.weekdaySat',
  'reportSubscriptions.weekdaySun',
]

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

export function formatFrequency(sub: ReportSubscription, t: TFunction): string {
  const time = `${String(sub.at_hour).padStart(2, '0')}:${String(sub.at_minute).padStart(2, '0')}`
  if (sub.frequency === 'weekly') {
    const day = t(WEEKDAYS[sub.day_of_week ?? 0])
    return t('reportSubscriptions.scheduleWeekly', { day, time })
  }
  if (sub.frequency === 'monthly') {
    return t('reportSubscriptions.scheduleMonthly', { day: sub.day_of_month ?? 1, time })
  }
  return t('reportSubscriptions.scheduleDaily', { time })
}
