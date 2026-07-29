import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { ICONS } from './Icons'

interface EmptyStateProps {
  title?: string
  description?: string
  icon?: keyof typeof ICONS
  size?: 'sm' | 'md' | 'lg'
  action?: ReactNode
  className?: string
}

export default function EmptyState({
  title,
  description,
  icon = 'empty',
  size = 'md',
  action,
  className = '',
}: EmptyStateProps) {
  const { t } = useTranslation()
  const resolvedTitle = title ?? t('common:status.empty')
  const resolvedDescription = description ?? t('common:empty.defaultHint')
  const Icon = ICONS[icon]
  const sizeCls = size === 'sm' ? 'empty-state-sm' : size === 'lg' ? 'empty-state-lg' : ''
  return (
    <div className={`empty-state ${sizeCls} ${className}`.trim()}>
      <div className="empty-state-icon" aria-hidden="true">
        <Icon size={size === 'sm' ? 32 : size === 'lg' ? 56 : 40} />
      </div>
      <h4 className="empty-state-title">{resolvedTitle}</h4>
      {resolvedDescription && <p className="empty-state-desc">{resolvedDescription}</p>}
      {action && <div className="empty-state-action">{action}</div>}
    </div>
  )
}
