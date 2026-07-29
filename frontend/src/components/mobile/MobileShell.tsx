import { useMemo, useState, type ReactNode } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../../context/AuthContext'
import { ICONS } from '../ui/Icons'
import LanguageSwitcher from '../LanguageSwitcher'
import NotificationBell from '../NotificationBell'
import { getMobileNav, flattenLeaves, matchNavItem } from './mobileNav'
import BottomTabBar from './BottomTabBar'
import BottomSheet from './BottomSheet'
import '../../i18n/mobile'

interface MobileShellProps {
  children: ReactNode
}

/**
 * 移动端外壳：顶部应用栏（品牌 + 当前页标题 + 通知 + 语言 + 头像登出）
 * + 可滚动内容区（管理类路由注入桌面优先提示）+ 底部 Tab 栏（更多走底部弹层）。
 * 复用统一导航数据源 NAV_SECTIONS，不另维护一份菜单。
 */
export default function MobileShell({ children }: MobileShellProps) {
  const { t } = useTranslation(['menu', 'common', 'auth', 'mobile'])
  const { role, username, logout } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const [moreOpen, setMoreOpen] = useState(false)

  const nav = useMemo(() => getMobileNav(role), [role])
  const allLeaves = useMemo(
    () => [...nav.primary, ...flattenLeaves(nav.moreSections)],
    [nav]
  )

  const labelText = (key: string): string => {
    const translated = t(key)
    if (translated && translated !== key) return translated
    return key.split('.').pop() ?? key
  }

  const titleItem = matchNavItem(allLeaves, location.pathname)
  const title = titleItem ? labelText(titleItem.labelKey) : t('mobile:title')

  const initial = (username || '?').slice(0, 1).toUpperCase()

  const handleLogout = async () => {
    await logout()
    navigate('/login', { replace: true })
  }

  return (
    <div className="mobile-shell">
      <header className="mobile-appbar">
        <div className="mobile-appbar__brand">
          <img src="/logo.svg" alt="FinPilot" className="mobile-appbar__logo" />
          <span className="mobile-appbar__title">{title}</span>
        </div>
        <div className="mobile-appbar__actions">
          <NotificationBell />
          <LanguageSwitcher />
          <button
            type="button"
            className="mobile-appbar__avatar"
            aria-label={username || t('auth:brand.tagline')}
            onClick={handleLogout}
          >
            {initial}
          </button>
        </div>
      </header>

      <main className="mobile-content">
        {children}
      </main>

      <BottomTabBar
        primary={nav.primary}
        activePath={location.pathname}
        onNavigate={(p) => navigate(p)}
        onMore={() => setMoreOpen(true)}
      />

      <BottomSheet open={moreOpen} onClose={() => setMoreOpen(false)} title={t('mobile:more')}>
        <nav className="mobile-more" aria-label={t('mobile:more')}>
          {nav.moreSections.map((section) => (
            <div key={section.titleKey} className="mobile-more__group">
              <div className="mobile-more__group-title">{labelText(section.titleKey)}</div>
              {section.items.map((item) => {
                const Icon = ICONS[item.icon]
                const active =
                  location.pathname === item.path ||
                  location.pathname.startsWith(item.path + '/')
                return (
                  <button
                    key={item.path}
                    type="button"
                    className={`mobile-more__item${active ? ' is-active' : ''}`}
                    aria-current={active ? 'page' : undefined}
                    onClick={() => {
                      setMoreOpen(false)
                      navigate(item.path)
                    }}
                  >
                    <span className="mobile-more__icon">
                      <Icon size={20} />
                    </span>
                    <span className="mobile-more__label">{labelText(item.labelKey)}</span>
                  </button>
                )
              })}
            </div>
          ))}
        </nav>
      </BottomSheet>
    </div>
  )
}
