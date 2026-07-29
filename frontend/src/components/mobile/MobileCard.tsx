import type { ReactNode } from 'react'

interface MobileCardProps {
  children: ReactNode
  onClick?: () => void
  className?: string
}

/** 触摸友好的大点击区卡片，移动端列表/卡片流的基础单元。 */
export default function MobileCard({ children, onClick, className }: MobileCardProps) {
  const cls = `mobile-card${className ? ' ' + className : ''}`
  if (onClick) {
    return (
      <button type="button" className={`${cls} is-clickable`} onClick={onClick}>
        {children}
      </button>
    )
  }
  return <div className={cls}>{children}</div>
}
