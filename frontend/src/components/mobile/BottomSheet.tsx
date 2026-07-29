import { useEffect, type ReactNode } from 'react'

interface BottomSheetProps {
  open: boolean
  onClose: () => void
  title?: string
  children: ReactNode
}

/** 通用底部弹层（移动端替代桌面侧滑抽屉/模态），点击遮罩或 Esc 关闭。 */
export default function BottomSheet({ open, onClose, title, children }: BottomSheetProps) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="mobile-sheet__overlay" onClick={onClose} role="presentation">
      <div
        className="mobile-sheet"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mobile-sheet__handle" />
        {title && <div className="mobile-sheet__title">{title}</div>}
        <div className="mobile-sheet__body">{children}</div>
      </div>
    </div>
  )
}
