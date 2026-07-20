import React, { useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
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
function breadcrumbPath(pathname: string): { label: string; path?: string }[] {
  const segments = pathname.split('/').filter(Boolean)
  const crumbs: { label: string; path?: string }[] = [{ label: '管理后台', path: '/admin' }]

  const labelMap: Record<string, string> = {
    models: '模型管理',
    prompts: '提示词管理',
    'prompt-deep': '提示词进阶',
    'runtime-logs': '运行记录',
    tools: '工具管理',
    'tool-monitoring': '工具监控',
    'context-management': '上下文管理',
    skills: '技能管理',
    'search-engines': '搜索引擎',
    'mcp-servers': 'MCP 服务器',
    'sandbox-configs': '沙箱配置',
    agents: 'Agent 配置',
    settings: '系统设置',
    'eval-management': '评估管理',
    'factor-mining': '因子挖掘',
    backtesting: '策略回测',
    'workflow-editor': '工作流编辑器',
  }

  for (let i = 1; i < segments.length; i++) {
    const seg = segments[i]
    crumbs.push({
      label: labelMap[seg] || seg,
      path: i < segments.length - 1 ? '/' + segments.slice(0, i + 1).join('/') : undefined,
    })
  }

  return crumbs
}

export default function AdminLayout() {
  const location = useLocation()
  const crumbs = breadcrumbPath(location.pathname)
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
                <span className="admin-breadcrumb-current">{crumb.label}</span>
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
              aria-label="实时通知"
              title="实时通知"
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
                    <strong>实时通知</strong>
                    <span className="admin-bell-header-actions">
                      <button type="button" onClick={() => markRead()} className="admin-bell-mini-btn">
                        全部已读
                      </button>
                      <button type="button" onClick={() => clear()} className="admin-bell-mini-btn">
                        清空
                      </button>
                    </span>
                  </div>
                  <div className="admin-bell-list">
                    {notifications.length === 0 ? (
                      <div className="admin-bell-empty">暂无通知</div>
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
