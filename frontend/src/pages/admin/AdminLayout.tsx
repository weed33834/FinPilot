import React, { useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ICONS } from '../../components/ui/Icons.tsx'
import RealtimeIndicator from '../../components/RealtimeIndicator.tsx'
import { useRealtimeNotifications } from '../../hooks/useRealtimeNotifications.ts'
import { formatDateTime } from '../../utils/format.ts'

/**
 * 管理后台内容布局
 *
 * 设计变更：
 * - 不再渲染二级侧栏（主 Sidebar 的"管理"分组已含全部子菜单）
 * - 不再渲染移动端抽屉（主 Sidebar 已处理移动端）
 * - 仅保留顶部条：面包屑 + 实时状态 + 通知铃铛 + Outlet
 * - 消除旧的"PrivateRoute/Layout + AdminLayout"双重 Sidebar 问题
 */

// 路径 segment → 面包屑 i18n key（admin:layout.breadcrumb.*）。新增 admin 子路由时在此登记。
const BREADCRUMB_SEGMENTS = [
  'models', 'prompts', 'prompt-deep', 'runtime-logs', 'tools', 'tool-monitoring',
  'context-management', 'skills', 'search-engines', 'mcp-servers', 'sandbox-configs',
  'agents', 'settings', 'eval-management', 'factor-mining', 'backtesting', 'workflow-editor',
] as const

function useBreadcrumb(pathname: string) {
  const { t } = useTranslation('admin')
  const segments = pathname.split('/').filter(Boolean)
  const crumbs: { label: string; path?: string }[] = [{ label: t('layout.adminHome'), path: '/admin' }]

  for (let i = 1; i < segments.length; i++) {
    const seg = segments[i]
    // 已登记的 segment 走 i18n，未登记的回退到原始路径段，避免面包屑空白
    const label = (BREADCRUMB_SEGMENTS as readonly string[]).includes(seg)
      ? t(`layout.breadcrumb.${seg}`)
      : seg
    crumbs.push({
      label,
      path: i < segments.length - 1 ? '/' + segments.slice(0, i + 1).join('/') : undefined,
    })
  }

  return crumbs
}

export default function AdminLayout() {
  const location = useLocation()
  const { t } = useTranslation('admin')
  const crumbs = useBreadcrumb(location.pathname)
  const { notifications, unreadCount, markRead, clear, status } = useRealtimeNotifications()
  const [bellOpen, setBellOpen] = useState(false)

  // 路由切换后自动关闭铃铛下拉
  React.useEffect(() => {
    setBellOpen(false)
  }, [location.pathname])

  return (
    <div className="admin-shell">
      <div className="admin-topbar">
        <nav className="admin-breadcrumb" aria-label="Breadcrumb">
          {crumbs.map((crumb, idx) => (
            <span key={idx} className="admin-breadcrumb-item">
              {idx > 0 && <span className="admin-breadcrumb-sep">/</span>}
              {crumb.path && idx < crumbs.length - 1 ? (
                <NavLink to={crumb.path} className="admin-breadcrumb-link">
                  {crumb.label}
                </NavLink>
              ) : (
                <span className="admin-breadcrumb-current" aria-current="page">{crumb.label}</span>
              )}
            </span>
          ))}
        </nav>

        <div className="admin-topbar-actions">
          <RealtimeIndicator status={status} />

          <div className="admin-bell-wrapper">
            <button
              type="button"
              onClick={() => setBellOpen((v) => !v)}
              className="admin-bell-btn"
              aria-label={t('layout.notifications')}
              title={t('layout.notifications')}
            >
              <ICONS.bell size={16} />
              {unreadCount > 0 && (
                <span className="admin-bell-badge">
                  {unreadCount > 99 ? '99+' : unreadCount}
                </span>
              )}
            </button>

            {bellOpen && (
              <>
                <div className="admin-bell-overlay" onClick={() => setBellOpen(false)} />
                <div className="admin-bell-dropdown">
                  <div className="admin-bell-header">
                    <strong>{t('layout.notifications')}</strong>
                    <span className="admin-bell-header-actions">
                      <button type="button" onClick={() => markRead()} className="admin-bell-mini-btn">
                        {t('layout.markAllRead')}
                      </button>
                      <button type="button" onClick={() => clear()} className="admin-bell-mini-btn">
                        {t('layout.clear')}
                      </button>
                    </span>
                  </div>
                  <div className="admin-bell-list">
                    {notifications.length === 0 ? (
                      <div className="admin-bell-empty">{t('layout.noNotifications')}</div>
                    ) : (
                      notifications.map((n) => (
                        <div key={n.id} className={`admin-bell-item${n.read ? ' read' : ''}`}>
                          <span className={`admin-bell-dot level-${n.level || 'info'}`} />
                          <div className="admin-bell-content">
                            <div className="admin-bell-title">{n.title}</div>
                            {n.message && <div className="admin-bell-message">{n.message}</div>}
                            <div className="admin-bell-time">{formatDateTime(n.timestamp)}</div>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      <div className="admin-page">
        <Outlet />
      </div>
    </div>
  )
}
