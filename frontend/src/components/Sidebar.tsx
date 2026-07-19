import { Link, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../context/AuthContext.tsx'
import LanguageSwitcher from './LanguageSwitcher.tsx'
import NotificationBell from './NotificationBell.tsx'
import { ICONS, type IconName } from './ui/Icons.tsx'

interface NavItem {
  path: string
  labelKey: string
  icon: IconName
}

interface NavSection {
  titleKey: string
  items: NavItem[]
}

interface SidebarProps {
  open: boolean
  onToggle: () => void
  onClose: () => void
}

export default function Sidebar({ open, onToggle, onClose }: SidebarProps) {
  const { t } = useTranslation(['common', 'menu'])
  const { role, username, logout } = useAuth()
  const location = useLocation()

  const isActive = (path: string) =>
    location.pathname === path || location.pathname.startsWith(path + '/')
  const canApprove = role === 'admin' || role === 'auditor'
  const isAdmin = role === 'admin'
  const canManageSubscriptions = role === 'admin' || role === 'finance_manager'

  const sections: NavSection[] = [
    {
      titleKey: 'menu:groups.workspace',
      items: [
        { path: '/dashboard', labelKey: 'menu:items.dashboard', icon: 'dashboard' },
        { path: '/reports', labelKey: 'menu:items.reports', icon: 'reports' },
        { path: '/documents', labelKey: 'menu:items.documents', icon: 'documents' },
        { path: '/queries', labelKey: 'menu:items.queries', icon: 'queries' },
        { path: '/kpi', labelKey: 'menu:items.kpi', icon: 'trend' },
        { path: '/agent', labelKey: 'menu:items.agent', icon: 'agent' },
        { path: '/conversations', labelKey: 'menu:items.conversations', icon: 'agent' },
        ...(canManageSubscriptions
          ? [{ path: '/report-subscriptions', labelKey: 'menu:items.reportSubscriptions', icon: 'subscriptions' as IconName }]
          : []),
        ...(canManageSubscriptions
          ? [{ path: '/report-templates', labelKey: 'menu:items.reportTemplates', icon: 'templates' as IconName }]
          : []),
        { path: '/security', labelKey: 'menu:items.security', icon: 'security' },
      ],
    },
    {
      titleKey: 'menu:groups.review',
      items: [
        ...(canApprove
          ? [{ path: '/approvals', labelKey: 'menu:items.approvals', icon: 'approvals' as IconName }]
          : []),
        ...(canApprove
          ? [{ path: '/hitl', labelKey: 'menu:items.hitl', icon: 'approvals' as IconName }]
          : []),
        { path: '/audit', labelKey: 'menu:items.audit', icon: 'audit' },
        ...(canApprove
          ? [{ path: '/reflections', labelKey: 'menu:items.reflections', icon: 'reflections' as IconName }]
          : []),
      ],
    },
    ...(isAdmin
      ? [
          {
            titleKey: 'menu:groups.management',
            items: [
              { path: '/users', labelKey: 'menu:items.users', icon: 'users' as IconName },
              { path: '/api-keys', labelKey: 'menu:items.apiKeys', icon: 'apiKeys' as IconName },
              { path: '/llm-providers', labelKey: 'menu:items.llmProviders', icon: 'llm' as IconName },
              { path: '/admin', labelKey: 'menu:items.admin', icon: 'settings' as IconName },
              { path: '/admin/runtime-logs', labelKey: 'menu:items.runtimeLogs', icon: 'audit' as IconName },
              { path: '/access-policies', labelKey: 'menu:items.accessPolicies', icon: 'policies' as IconName },
              { path: '/settings', labelKey: 'menu:items.settings', icon: 'settings' as IconName },
            ],
          },
        ]
      : []),
  ]

  const initial = (username || '?').slice(0, 1).toUpperCase()
  const roleKey = role ? `common:role.${role}` : ''
  const roleLabel = roleKey ? t(roleKey) : ''

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
        <div className="sidebar-brand">
          <div className="sidebar-brand-icon">FP</div>
          <div className="sidebar-brand-text">
            <h2>{t('common:common.appName')}</h2>
            <p>FINANCIAL ANALYSIS</p>
          </div>
        </div>

        <nav className="sidebar-nav" aria-label={t('menu:actions.mainNav')}>
          {sections.map((section) => (
            <div key={section.titleKey} className="sidebar-section">
              <div className="sidebar-section-title">{t(section.titleKey)}</div>
              {section.items.map((item) => {
                const Icon = ICONS[item.icon]
                return (
                  <Link
                    key={item.path}
                    to={item.path}
                    className={`sidebar-link${isActive(item.path) ? ' active' : ''}`}
                    onClick={onClose}
                  >
                    <Icon />
                    <span>{t(item.labelKey)}</span>
                  </Link>
                )
              })}
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
