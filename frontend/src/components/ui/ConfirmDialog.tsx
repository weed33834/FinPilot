import { useEffect, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import Modal from './Modal.tsx'

export type ConfirmVariant = 'danger' | 'warning' | 'info'

export interface ConfirmDialogProps {
  open: boolean
  title: string
  message: ReactNode
  confirmText?: string
  cancelText?: string
  variant?: ConfirmVariant
  onConfirm: () => void | Promise<void>
  onCancel: () => void
  busy?: boolean
}

const ICON_PATHS: Record<ConfirmVariant, string> = {
  danger:
    'M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M10 11v6M14 11v6',
  warning:
    'M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0zM12 9v4M12 17h.01',
  info: 'M12 22a10 10 0 1 1 0-20 10 10 0 0 1 0 20zM12 16v-4M12 8h.01',
}

function ConfirmIcon({ variant }: { variant: ConfirmVariant }) {
  const color =
    variant === 'danger'
      ? 'var(--color-danger)'
      : variant === 'warning'
        ? 'var(--color-warning)'
        : 'var(--color-info)'
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: '36px',
        height: '36px',
        borderRadius: '50%',
        background: `color-mix(in srgb, ${color} 15%, transparent)`,
        color,
        flexShrink: 0,
      }}
      aria-hidden="true"
    >
      <svg
        width="20"
        height="20"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d={ICON_PATHS[variant]} />
      </svg>
    </span>
  )
}

export default function ConfirmDialog({
  open,
  title,
  message,
  confirmText = '确认',
  cancelText = '取消',
  variant = 'danger',
  onConfirm,
  onCancel,
  busy = false,
}: ConfirmDialogProps) {
  const [submitting, setSubmitting] = useState(false)
  const isBusy = busy || submitting

  const handleConfirm = async () => {
    setSubmitting(true)
    try {
      await onConfirm()
    } finally {
      setSubmitting(false)
    }
  }

  if (!open) return null

  const confirmClass = variant === 'danger' ? 'danger' : 'btn-primary'

  return (
    <Modal
      title={title}
      onClose={onCancel}
      footer={
        <>
          <button type="button" className="secondary" onClick={onCancel} disabled={isBusy}>
            {cancelText}
          </button>
          <button
            type="button"
            className={confirmClass}
            onClick={handleConfirm}
            disabled={isBusy}
          >
            {isBusy ? '处理中...' : confirmText}
          </button>
        </>
      }
    >
      <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
        <ConfirmIcon variant={variant} />
        <div style={{ flex: 1, paddingTop: '4px' }}>{message}</div>
      </div>
    </Modal>
  )
}

// ==================== 命令式 confirm() API ====================
// 与 toast 一致的全局 store + portal 模式：confirm() 返回 Promise<boolean>，
// 由挂载在 App 根节点的 <ConfirmRoot /> 统一渲染。同一时刻只展示一个确认框，后续调用排队。

export interface ConfirmOptions {
  title: string
  message: ReactNode
  confirmText?: string
  cancelText?: string
  variant?: ConfirmVariant
}

interface PendingConfirm extends ConfirmOptions {
  id: string
  resolve: (ok: boolean) => void
}

const confirmQueue: PendingConfirm[] = []
let currentConfirm: PendingConfirm | null = null
let confirmListeners: Array<(pending: PendingConfirm | null) => void> = []
let confirmCounter = 0

function emitConfirm() {
  for (const listener of confirmListeners) listener(currentConfirm)
}

function activateNext() {
  if (currentConfirm || confirmQueue.length === 0) return
  currentConfirm = confirmQueue.shift() ?? null
  emitConfirm()
}

function settleConfirm(ok: boolean) {
  const pending = currentConfirm
  currentConfirm = null
  emitConfirm()
  pending?.resolve(ok)
  // 让当前确认框卸载后再激活队列中的下一个，避免动画/焦点重叠
  window.setTimeout(activateNext, 0)
}

export function confirm(options: ConfirmOptions): Promise<boolean> {
  return new Promise<boolean>((resolve) => {
    const pending: PendingConfirm = {
      id: `confirm-${++confirmCounter}`,
      resolve,
      ...options,
    }
    confirmQueue.push(pending)
    activateNext()
  })
}

export function ConfirmRoot() {
  const [pending, setPending] = useState<PendingConfirm | null>(currentConfirm)

  useEffect(() => {
    confirmListeners.push(setPending)
    return () => {
      confirmListeners = confirmListeners.filter((l) => l !== setPending)
    }
  }, [])

  if (!pending) return null

  const variant: ConfirmVariant = pending.variant ?? 'danger'
  const confirmText = pending.confirmText ?? '确认'
  const cancelText = pending.cancelText ?? '取消'
  const confirmClass = variant === 'danger' ? 'danger' : 'btn-primary'

  return createPortal(
    <Modal
      title={pending.title}
      onClose={() => settleConfirm(false)}
      footer={
        <>
          <button type="button" className="secondary" onClick={() => settleConfirm(false)}>
            {cancelText}
          </button>
          <button type="button" className={confirmClass} onClick={() => settleConfirm(true)}>
            {confirmText}
          </button>
        </>
      }
    >
      <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
        <ConfirmIcon variant={variant} />
        <div style={{ flex: 1, paddingTop: '4px' }}>{pending.message}</div>
      </div>
    </Modal>,
    document.body,
  )
}
