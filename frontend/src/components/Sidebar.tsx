import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../context/AuthContext.tsx'
import LanguageSwitcher from './LanguageSwitcher.tsx'
import NotificationBell from './NotificationBell.tsx'
import { ICONS } from './ui/Icons.tsx'
import {
  NAV_SECTIONS,
  NAV_FALLBACK_LABELS,
  filterNavByRole,
  type NavItem,
} from '../utils/navigation.ts'
import { ROLE_LABELS, type RoleKey } from '../utils/permissions.ts'

interface SidebarProps {
  open: boolean
  onToggle: () => void
  onClose: () => void
}

export default function Sidebar({ open, onToggle, onClose }: SidebarProps) {
  const { t } = useTranslation(['common', 'menu'])
  const { role, username, logout } = useAuth()
  const location = useLocation()

  // 角色过滤后的导航数据
  const sections = filterNavByRole(NAV_SECTIONS, role)

  // 已展开的分组路径集合（仅对带 children 的项生效）
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  // 解析 i18n 标签，缺失时回退到 NAV_FALLBACK_LABELS
  const labelText = (key: string): string => {
    const translated = t(key)
    if (translated && translated !== key) return translated
    return NAV_FALLBACK_LABELS[key] ?? key
  }

  // 路由切换后：自动展开包含当前路径的分组 + 关闭移动端抽屉
  useEffect(() => {
    setExpanded((prev) => {
      const next = new Set(prev)
      for (const section of sections) {
        for (const item of section.items) {
          if (item.children) {
            const hit = item.children.some(
              (child) => child.path === location.pathname || location.pathname.startsWith(child.path + '/')
            )
            if (hit) next.add(item.path)
          }
        }
      }
      return next
    })
  }, [location.pathname, sections])

  const isActive = (path: string) =>
    location.pathname === path || location.pathname.startsWith(path + '/')

  const toggleGroup = (path: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(path)) next.delete(path)
      else next.add(path)
      return next
    })
  }

  const roleLabel = role ? ROLE_LABELS[role as RoleKey] ?? t(`common:role.${role}`) : ''
  const initial = (username || '?').slice(0, 1).toUpperCase()

  return (
    <>
      <button
        className="sidebar-toggle"
        aria-label={open ? t('menu:actions.closeMenu') : t('menu:actions.toggleMenu')}
        aria-expanded={open}
        onClick={onToggle}
      >
        {open ? <ICONS.close size={20} /> : <ICONS.menu size={20} />}
      </button>

      <aside className={`sidebar${open ? ' open' : ''}`}>
        <Link to="/agent" className="sidebar-brand" onClick={onClose} aria-label="FinPilot home">
          <div className="sidebar-brand-icon">FP</div>
          <div className="sidebar-brand-text">
            <h2>{t('common:common.appName')}</h2>
            <p>FINANCIAL ANALYSIS</p>
          </div>
        </Link>

        <nav className="sidebar-nav" aria-label={t('menu:actions.mainNav')}>
          {sections.map((section) => (
            <div key={section.titleKey} className="sidebar-section">
              <div className="sidebar-section-title">{labelText(section.titleKey)}</div>
              {section.items.map((item) => (
                <SidebarNode
                  key={item.path}
                  item={item}
                  isActive={isActive}
                  isExpanded={expanded.has(item.path)}
                  onToggle={toggleGroup}
                  labelText={labelText}
                  onClose={onClose}
                />
              ))}
            </div>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="sidebar-user">
            <div className="sidebar-user-avatar">{initial}</div>
            <div className="sidebar-user-info">
              <div className="sidebar-user-name">{username || t('menu:actions.notLoggedIn')}</div>
              <div className="sidebar-user-role">{roleLabel}</div>
            </div>
          </div>
          <div className="sidebar-footer-actions">
            <NotificationBell />
            <LanguageSwitcher />
            <button
              className="sidebar-logout"
              title={t('menu:actions.logout')}
              aria-label={t('menu:actions.logout')}
              onClick={logout}
            >
              <ICONS.logout size={18} />
            </button>
          </div>
        </div>
      </aside>

      {open && <div className="sidebar-overlay open" onClick={onClose} aria-hidden="true" />}
    </>
  )
}

interface SidebarNodeProps {
  item: NavItem
  isActive: (path: string) => boolean
  isExpanded: boolean
  onToggle: (path: string) => void
  labelText: (key: string) => string
  onClose: () => void
}

function SidebarNode({ item, isActive, isExpanded, onToggle, labelText, onClose }: SidebarNodeProps) {
  const Icon = ICONS[item.icon]
  const hasChildren = !!item.children && item.children.length > 0
  const active = isActive(item.path)

  if (hasChildren) {
    return (
      <div className={`sidebar-nav-group${isExpanded ? ' expanded' : ''}${active ? ' contains-active' : ''}`}>
        <button
          type="button"
          className={`sidebar-nav-group-header${active ? ' active' : ''}`}
          onClick={() => onToggle(item.path)}
          aria-expanded={isExpanded}
        >
          <span className="sidebar-nav-icon">
            <Icon />
          </span>
          <span className="sidebar-nav-label">{labelText(item.labelKey)}</span>
          <span className={`sidebar-nav-chevron${isExpanded ? ' rotated' : ''}`} aria-hidden="true">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </span>
        </button>
        <div className="sidebar-nav-children">
          {item.children!.map((child) => {
            const ChildIcon = ICONS[child.icon]
            const childActive = isActive(child.path)
            return (
              <Link
                key={child.path}
                to={child.path}
                className={`sidebar-link sidebar-link-child${childActive ? ' active' : ''}`}
                onClick={onClose}
              >
                <span className="sidebar-nav-icon">
                  <ChildIcon />
                </span>
                <span>{labelText(child.labelKey)}</span>
              </Link>
            )
          })}
        </div>
      </div>
    )
  }

  return (
    <Link
      to={item.path}
      className={`sidebar-link${active ? ' active' : ''}`}
      onClick={onClose}
    >
      <span className="sidebar-nav-icon">
        <Icon />
      </span>
      <span>{labelText(item.labelKey)}</span>
      {item.badge && (
        <span className={`sidebar-tag sidebar-tag-${item.badge}`}>
          {item.badge === 'new' ? 'NEW' : 'BETA'}
        </span>
      )}
    </Link>
  )
}
