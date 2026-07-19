import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { ICONS } from './Icons'

interface ModalProps {
  title: string
  children: ReactNode
  footer?: ReactNode
  onClose: () => void
}

const FOCUSABLE_SELECTOR =
  'button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"]):not(:disabled)'

const EXIT_ANIMATION_MS = 160

export default function Modal({ title, children, footer, onClose }: ModalProps) {
  const titleId = useId()
  const panelRef = useRef<HTMLDivElement>(null)
  const closeButtonRef = useRef<HTMLButtonElement>(null)
  const previouslyFocusedRef = useRef<HTMLElement | null>(null)
  const [closing, setClosing] = useState(false)

  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose

  const handleClose = () => {
    if (closing) return
    setClosing(true)
    window.setTimeout(() => {
      onCloseRef.current()
    }, EXIT_ANIMATION_MS)
  }

  useEffect(() => {
    previouslyFocusedRef.current = document.activeElement as HTMLElement | null

    const originalOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    requestAnimationFrame(() => {
      if (!panelRef.current) return
      const focusable = Array.from(
        panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
      )
      const inputEl = focusable.find(
        (el) =>
          el.tagName === 'INPUT' ||
          el.tagName === 'TEXTAREA' ||
          el.tagName === 'SELECT',
      )
      const target = inputEl ?? focusable[0] ?? closeButtonRef.current
      target?.focus()
    })

    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        handleClose()
        return
      }
      if (e.key === 'Tab' && panelRef.current) {
        const focusable = Array.from(
          panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
        )
        if (focusable.length === 0) return
        const first = focusable[0]
        const last = focusable[focusable.length - 1]
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault()
          last.focus()
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault()
          first.focus()
        }
      }
    }
    document.addEventListener('keydown', handler)

    return () => {
      document.removeEventListener('keydown', handler)
      document.body.style.overflow = originalOverflow
      previouslyFocusedRef.current?.focus()
    }
  }, [])

  return (
    <div
      className={`modal-backdrop${closing ? ' closing' : ''}`}
      onClick={handleClose}
      role="presentation"
    >
      <div
        ref={panelRef}
        className="modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        <div className="modal-header">
          <h3 id={titleId}>{title}</h3>
          <button
            ref={closeButtonRef}
            className="ghost"
            onClick={handleClose}
            aria-label="关闭"
          >
            <ICONS.close size={18} />
          </button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-footer">{footer}</div>}
      </div>
    </div>
  )
}
