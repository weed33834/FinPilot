import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'

export type ToastVariant = 'success' | 'error' | 'warning' | 'info'

export interface ToastOptions {
  title?: string
  description?: string
  variant?: ToastVariant
  duration?: number
}

interface ToastItem extends Required<Omit<ToastOptions, 'description' | 'title'>> {
  id: string
  title?: string
  description?: string
  closing: boolean
}

const MAX_VISIBLE = 5
const TOAST_GAP_MS = 40

let listeners: Array<(toasts: ToastItem[]) => void> = []
let store: ToastItem[] = []
let idCounter = 0
const timers = new Map<string, number>()

function emit() {
  for (const l of listeners) l(store)
}

function dismiss(id: string) {
  const t = store.find((x) => x.id === id)
  if (!t) return
  if (t.closing) return
  t.closing = true
  emit()
  const timer = timers.get(id)
  if (timer) {
    window.clearTimeout(timer)
    timers.delete(id)
  }
  window.setTimeout(() => {
    store = store.filter((x) => x.id !== id)
    emit()
  }, 180)
}

function show(options: ToastOptions): string {
  const id = `toast-${++idCounter}`
  const variant: ToastVariant = options.variant ?? 'info'
  const duration = options.duration ?? 4000
  const item: ToastItem = {
    id,
    title: options.title,
    description: options.description,
    variant,
    duration,
    closing: false,
  }
  // 排序优先级：error > warning > info > success，保证 error 始终在最上方
  const PRIORITY: Record<ToastVariant, number> = { error: 0, warning: 1, info: 2, success: 3 }
  const sorted = [...store, item].sort(
    (a, b) => PRIORITY[a.variant] - PRIORITY[b.variant],
  )
  store = sorted.slice(-MAX_VISIBLE)
  emit()
  const timer = window.setTimeout(() => dismiss(id), duration)
  timers.set(id, timer)
  return id
}

export const toast = {
  success: (title: string, description?: string) => show({ title, description, variant: 'success' }),
  error: (title: string, description?: string) => show({ title, description, variant: 'error' }),
  warning: (title: string, description?: string) => show({ title, description, variant: 'warning' }),
  info: (title: string, description?: string) => show({ title, description, variant: 'info' }),
  show,
  dismiss,
}

const VARIANT_ICON_D: Record<ToastVariant, string> = {
  success: 'M20 6L9 17l-5-5',
  error: 'M18 6 6 18M6 6l12 12',
  warning: 'M12 9v4M12 17h.01M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z',
  info: 'M12 16v-4M12 8h.01M12 22a10 10 0 1 1 0-20 10 10 0 0 1 0 20z',
}

function ToastIcon({ variant }: { variant: ToastVariant }) {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={VARIANT_ICON_D[variant]} />
    </svg>
  )
}

function CloseIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M18 6 6 18M6 6l12 12" />
    </svg>
  )
}

export function Toaster() {
  const [toasts, setToasts] = useState<ToastItem[]>(store)
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    listeners.push(setToasts)
    setMounted(true)
    return () => {
      listeners = listeners.filter((l) => l !== setToasts)
    }
  }, [])

  if (!mounted) return null

  return createPortal(
    <div className="toast-container" role="region" aria-label="通知" aria-live="polite">
      {toasts.map((t, i) => (
        <div
          key={t.id}
          className={`toast toast-${t.variant}${t.closing ? ' closing' : ''}`}
          role={t.variant === 'error' ? 'alert' : 'status'}
          style={
            {
              ['--toast-duration' as never]: `${Math.max(t.duration - i * TOAST_GAP_MS, 800)}ms`,
            } as React.CSSProperties
          }
        >
          <span className="toast-icon" aria-hidden="true">
            <ToastIcon variant={t.variant} />
          </span>
          <div className="toast-content">
            {t.title && <p className="toast-title">{t.title}</p>}
            {t.description && <p className="toast-desc">{t.description}</p>}
          </div>
          <button
            type="button"
            className="toast-close"
            onClick={() => dismiss(t.id)}
            aria-label="关闭通知"
          >
            <CloseIcon />
          </button>
        </div>
      ))}
    </div>,
    document.body,
  )
}
