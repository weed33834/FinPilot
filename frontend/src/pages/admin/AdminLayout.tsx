import React, { useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { ICONS } from '../../components/ui/Icons.tsx'
import RealtimeIndicator from '../../components/RealtimeIndicator.tsx'
import { useRealtimeNotifications } from '../../hooks/useRealtimeNotifications.ts'
import { formatDateTime } from '../../utils/format.ts'

interface AdminMenuItem {
  path: string
  label: string
  icon: React.ReactNode
  disabled?: boolean
}

const adminMenuItems: AdminMenuItem[] = [
  { path: '/admin', label: '概览', icon: <ICONS.dashboard /> },
  { path: '/admin/models', label: '模型管理', icon: <ICONS.llm /> },
  { path: '/admin/prompts', label: '提示词管理', icon: <ICONS.documents /> },
  { path: '/admin/prompt-deep', label: '提示词进阶', icon: <ICONS.copy /> },
  { path: '/admin/runtime-logs', label: '运行记录', icon: <ICONS.audit /> },
  { path: '/admin/tools', label: '工具管理', icon: <ICONS.queries /> },
  { path: '/admin/tool-monitoring', label: '工具监控', icon: <ICONS.audit /> },
  { path: '/admin/context-management', label: '上下文管理', icon: <ICONS.security /> },
  { path: '/admin/skills', label: '技能管理', icon: <ICONS.templates /> },
  { path: '/admin/search-engines', label: '搜索引擎', icon: <ICONS.search /> },
  { path: '/admin/mcp-servers', label: 'MCP 服务器', icon: <ICONS.apiKeys /> },
  { path: '/admin/sandbox-configs', label: '沙箱配置', icon: <ICONS.security /> },
  { path: '/admin/agents', label: 'Agent 配置', icon: <ICONS.agent /> },
  { path: '/admin/settings', label: '系统设置', icon: <ICONS.settings /> },
  { path: '/admin/eval-management', label: '评估管理', icon: <ICONS.queries /> },
  { path: '/admin/factor-mining', label: '因子挖掘', icon: <ICONS.trend /> },
  { path: '/admin/backtesting', label: '策略回测', icon: <ICONS.refresh /> },
  { path: '/admin/workflow-editor', label: '工作流编辑器', icon: <ICONS.templates /> },
]

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
  const [mobileNavOpen, setMobileNavOpen] = useState(false)

  // 路由切换后自动关闭移动端抽屉
  React.useEffect(() => {
    setMobileNavOpen(false)
    setBellOpen(false)
  }, [location.pathname])

  return (
    <div className={`admin-layout${mobileNavOpen ? ' mobile-nav-open' : ''}`}>
      {/* 移动端遮罩 */}
      <div
        className={`admin-mobile-overlay${mobileNavOpen ? ' open' : ''}`}
        onClick={() => setMobileNavOpen(false)}
        aria-hidden={!mobileNavOpen}
      />

      {/* 左侧二级侧边栏 */}
      <aside className={`admin-sidebar${mobileNavOpen ? ' open' : ''}`}>
        <div className="admin-sidebar-header">
          <ICONS.settings size={18} />
          <span>管理后台</span>
          <button
            type="button"
            className="admin-sidebar-close"
            onClick={() => setMobileNavOpen(false)}
            aria-label="关闭菜单"
          >
            ✕
          </button>
        </div>
        <nav className="admin-sidebar-nav">
          {adminMenuItems.map((item) => {
            const isActive =
              item.path === '/admin'
                ? location.pathname === '/admin'
                : location.pathname.startsWith(item.path)

            if (item.disabled) {
              return (
                <div
                  key={item.path}
                  className="admin-nav-item disabled"
                  title={`${item.label} — 即将上线`}
                >
                  <span className="admin-nav-icon">{item.icon}</span>
                  <span className="admin-nav-label">{item.label}</span>
                  <span className="nav-badge">即将上线</span>
                </div>
              )
            }

            return (
              <NavLink
                key={item.path}
                to={item.path}
                className={`admin-nav-item${isActive ? ' active' : ''}`}
              >
                <span className="admin-nav-icon">{item.icon}</span>
                <span className="admin-nav-label">{item.label}</span>
              </NavLink>
            )
          })}
        </nav>
      </aside>

      {/* 右侧内容区 */}
      <div className="admin-content">
        {/* 移动端菜单触发器 */}
        <button
          type="button"
          className="admin-mobile-toggle"
          onClick={() => setMobileNavOpen((v) => !v)}
          aria-label="打开管理菜单"
          aria-expanded={mobileNavOpen}
        >
          <span className="admin-mobile-toggle-bar" />
          <span className="admin-mobile-toggle-bar" />
          <span className="admin-mobile-toggle-bar" />
        </button>
        {/* 顶栏：面包屑 + 实时状态 + 通知 */}
        <div
          className="admin-topbar"
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 12,
            padding: '8px 4px',
          }}
        >
          <nav className="admin-breadcrumb">
            {crumbs.map((crumb, idx) => (
              <span key={idx}>
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

          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <RealtimeIndicator status={status} />

            <div style={{ position: 'relative' }}>
              <button
                type="button"
                onClick={() => setBellOpen((v) => !v)}
                aria-label="实时通知"
                title="实时通知"
                style={{
                  position: 'relative',
                  background: 'transparent',
                  border: '1px solid var(--color-border,#3a3f4b)',
                  borderRadius: 8,
                  width: 34,
                  height: 34,
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  cursor: 'pointer',
                  color: 'var(--color-text,#e6e6e6)',
                }}
              >
                <ICONS.bell size={16} />
                {unreadCount > 0 && (
                  <span
                    style={{
                      position: 'absolute',
                      top: -6,
                      right: -6,
                      minWidth: 16,
                      height: 16,
                      padding: '0 4px',
                      borderRadius: 8,
                      background: '#ef4444',
                      color: '#fff',
                      fontSize: 10,
                      lineHeight: '16px',
                      textAlign: 'center',
                      fontWeight: 700,
                    }}
                  >
                    {unreadCount > 99 ? '99+' : unreadCount}
                  </span>
                )}
              </button>

              {bellOpen && (
                <>
                  <div
                    onClick={() => setBellOpen(false)}
                    style={{ position: 'fixed', inset: 0, zIndex: 40 }}
                  />
                  <div
                    style={{
                      position: 'absolute',
                      top: 40,
                      right: 0,
                      width: 340,
                      maxHeight: 420,
                      display: 'flex',
                      flexDirection: 'column',
                      background: 'var(--color-card,#1e2230)',
                      border: '1px solid var(--color-border,#3a3f4b)',
                      borderRadius: 10,
                      boxShadow: '0 10px 30px rgba(0,0,0,0.4)',
                      zIndex: 41,
                      overflow: 'hidden',
                    }}
                  >
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        padding: '8px 12px',
                        borderBottom: '1px solid var(--color-border,#3a3f4b)',
                        fontSize: '0.8rem',
                      }}
                    >
                      <strong>实时通知</strong>
                      <span style={{ display: 'flex', gap: 8 }}>
                        <button
                          type="button"
                          onClick={() => markRead()}
                          style={miniBtnStyle}
                        >
                          全部已读
                        </button>
                        <button type="button" onClick={() => clear()} style={miniBtnStyle}>
                          清空
                        </button>
                      </span>
                    </div>
                    <div style={{ overflowY: 'auto', flex: 1 }}>
                      {notifications.length === 0 ? (
                        <div
                          style={{
                            padding: 24,
                            textAlign: 'center',
                            color: 'var(--color-text-muted,#9aa)',
                            fontSize: '0.8rem',
                          }}
                        >
                          暂无通知
                        </div>
                      ) : (
                        notifications.map((n) => (
                          <div
                            key={n.id}
                            style={{
                              display: 'flex',
                              gap: 10,
                              padding: '10px 12px',
                              borderBottom: '1px solid var(--color-border,#2a2f3b)',
                              opacity: n.read ? 0.6 : 1,
                            }}
                          >
                            <span
                              style={{
                                width: 8,
                                height: 8,
                                borderRadius: '50%',
                                marginTop: 5,
                                flexShrink: 0,
                                background:
                                  n.level === 'error'
                                    ? '#ef4444'
                                    : n.level === 'warning'
                                      ? '#eab308'
                                      : n.level === 'success'
                                        ? '#22c55e'
                                        : '#3b82f6',
                              }}
                            />
                            <div style={{ minWidth: 0, flex: 1 }}>
                              <div style={{ fontSize: '0.8rem', fontWeight: 600 }}>
                                {n.title}
                              </div>
                              {n.message && (
                                <div
                                  style={{
                                    fontSize: '0.75rem',
                                    color: 'var(--color-text-muted,#9aa)',
                                    marginTop: 2,
                                    wordBreak: 'break-word',
                                  }}
                                >
                                  {n.message}
                                </div>
                              )}
                              <div
                                style={{
                                  fontSize: '0.68rem',
                                  color: 'var(--color-text-muted,#7a7f8c)',
                                  marginTop: 4,
                                }}
                              >
                                {formatDateTime(n.timestamp)}
                              </div>
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
    </div>
  )
}

const miniBtnStyle: React.CSSProperties = {
  background: 'transparent',
  border: '1px solid var(--color-border,#3a3f4b)',
  color: 'var(--color-text-muted,#9aa)',
  borderRadius: 6,
  padding: '2px 8px',
  fontSize: '0.7rem',
  cursor: 'pointer',
}
