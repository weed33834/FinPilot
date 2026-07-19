import { useTranslation } from 'react-i18next'

interface BadgeProps {
  status: string
  label?: string
}

const STATUS_I18N_KEYS: Record<string, string> = {
  pending: 'dashboard:status.pending',
  processing: 'dashboard:status.processing',
  success: 'dashboard:status.success',
  failed: 'dashboard:status.failed',
  needs_review: 'dashboard:status.needs_review',
  reviewing: 'dashboard:status.reviewing',
  approved: 'dashboard:status.approved',
  rejected: 'dashboard:status.rejected',
  draft: 'dashboard:status.draft',
  published: 'dashboard:status.published',
  parsed: 'dashboard:status.parsed',
  uploaded: 'dashboard:status.uploaded',
  completed: 'dashboard:status.completed',
}

export default function Badge({ status, label }: BadgeProps) {
  const { t } = useTranslation(['common', 'dashboard'])
  const i18nKey = STATUS_I18N_KEYS[status]
  const displayLabel = label || (i18nKey ? t(i18nKey) : status)
  return <span className={`badge ${status}`}>{displayLabel}</span>
}
