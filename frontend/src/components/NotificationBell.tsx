import { useEffect, useRef, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client.ts'
import { ICONS } from './ui/Icons.tsx'
import { getErrorMessage } from '../utils/errors.ts'
import type { Notification } from '../types/notification.ts'

function formatRelative(iso: string, t: (k: string, opts?: Record<string, unknown>) => string): string {
  const created = new Date(iso).getTime()
  if (Number.isNaN(created)) return ''
  const diffSec = Math.max(0, Math.floor((Date.now() - created) / 1000))
  if (diffSec < 60) return t('common:notifications.justNow')
  const diffMin = Math.floor(diffSec / 60)
  if (diffMin < 60) return t('common:notifications.minutesAgo', { count: diffMin })
  const diffHr = Math.floor(diffMin / 60)
  if (diffHr < 24) return t('common:notifications.hoursAgo', { count: diffHr })
  const diffDay = Math.floor(diffHr / 24)
  return t('common:notifications.daysAgo', { count: diffDay })
}

function getChannelIcon(channel: string) {
  if (channel.includes('approval')) return ICONS.approvals
  if (channel.includes('report')) return ICONS.reports
  if (channel.includes('document')) return ICONS.documents
  if (channel.includes('agent')) return ICONS.agent
  if (channel.includes('security')) return ICONS.security
  if (channel.includes('system')) return ICONS.settings
  return ICONS.bell
}

export default function NotificationBell() {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [closing, setClosing] = useState(false)
  const [items, setItems] = useState<Notification[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const wrapRef = useRef<HTMLDivElement>(null)

  const fetchNotifications = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const resp = await api.get('/notifications', { params: { page: 1, page_size: 20 } })
      const data = resp.data?.data
      const list: Notification[] = data?.items ?? data?.notifications ?? data ?? []
      setItems(Array.isArray(list) ? list : [])
    } catch (err) {
      // 后端可能尚未实现该端点 - 静默降级
      setError(getErrorMessage(err, t('common:notifications.loadFailed')))
      setItems([])
    } finally {
      setLoading(false)
    }
  }, [t])

  useEffect(() => {
    if (open) void fetchNotifications()
  }, [open, fetchNotifications])

  // 点击外部关闭
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) closeDropdown()
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  // ESC 关闭
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeDropdown()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const closeDropdown = () => {
    if (closing) return
    setClosing(true)
    window.setTimeout(() => {
      setOpen(false)
      setClosing(false)
    }, 140)
  }

  const handleToggle = () => {
    if (open) {
      closeDropdown()
    } else {
      setOpen(true)
    }
  }

  const markRead = async (id: string) => {
    setItems((prev) => prev.map((n) => (n.id === id ? { ...n, is_read: true } : n)))
    try {
      await api.post(`/notifications/${id}/read`)
    } catch {
      // 静默失败
    }
  }

  const unreadCount = items.filter((n) => !n.is_read).length

  return (
    <div className="notification-bell-wrap" ref={wrapRef}>
      <button
        type="button"
        className="notification-bell"
        onClick={handleToggle}
        aria-label={t('common:notifications.title')}
        aria-expanded={open}
        aria-haspopup="dialog"
      >
        <ICONS.bell size={18} />
        {unreadCount > 0 && (
          <span className="notification-bell-dot" aria-label={`${unreadCount} 未读`}>
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div
          className={`notification-dropdown${closing ? ' closing' : ''}`}
          role="dialog"
          aria-label={t('common:notifications.title')}
        >
          <div className="notification-header">
            <span>{t('common:notifications.title')}</span>
            <button
              type="button"
              className="ghost"
              onClick={() => void fetchNotifications()}
              disabled={loading}
              aria-label={t('common:notifications.refresh')}
            >
              {loading ? `${t('common:notifications.refreshing')}…` : t('common:notifications.refresh')}
            </button>
          </div>
          <div className="notification-list">
            {loading && items.length === 0 ? (
              <div className="notification-empty">{t('common:status.loading')}</div>
            ) : error ? (
              <div className="notification-empty">{error}</div>
            ) : items.length === 0 ? (
              <div className="notification-empty">{t('common:notifications.empty')}</div>
            ) : (
              items.map((n) => {
                const Icon = getChannelIcon(n.channel)
                return (
                  <div
                    key={n.id}
                    className={`notification-item${n.is_read ? '' : ' unread'}`}
                    role="button"
                    tabIndex={0}
                    onClick={() => markRead(n.id)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault()
                        markRead(n.id)
                      }
                    }}
                  >
                    <span className="notification-icon" aria-hidden="true">
                      <Icon size={14} />
                    </span>
                    <div className="notification-content">
                      <div className="notification-title">{n.title}</div>
                      {n.content && <div className="notification-desc">{n.content}</div>}
                      <div className="notification-time">{formatRelative(n.created_at, t)}</div>
                    </div>
                  </div>
                )
              })
            )}
          </div>
        </div>
      )}
    </div>
  )
}
