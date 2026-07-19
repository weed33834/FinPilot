import type { ReactNode } from 'react'
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
  title = '暂无数据',
  description = '当前列表为空，开始添加第一条记录吧。',
  icon = 'empty',
  size = 'md',
  action,
  className = '',
}: EmptyStateProps) {
  const Icon = ICONS[icon]
  const sizeCls = size === 'sm' ? 'empty-state-sm' : size === 'lg' ? 'empty-state-lg' : ''
  return (
    <div className={`empty-state ${sizeCls} ${className}`.trim()}>
      <div className="empty-state-icon" aria-hidden="true">
        <Icon size={size === 'sm' ? 32 : size === 'lg' ? 56 : 40} />
      </div>
      <h4 className="empty-state-title">{title}</h4>
      {description && <p className="empty-state-desc">{description}</p>}
      {action && <div className="empty-state-action">{action}</div>}
    </div>
  )
}
