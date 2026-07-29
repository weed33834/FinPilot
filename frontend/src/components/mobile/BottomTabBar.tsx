import { useTranslation } from 'react-i18next'
import { ICONS } from '../ui/Icons'
import type { NavItem } from '../../utils/navigation'
import '../../i18n/mobile'

interface BottomTabBarProps {
  primary: NavItem[]
  activePath: string
  onNavigate: (path: string) => void
  onMore: () => void
}

function isActive(itemPath: string, activePath: string): boolean {
  return activePath === itemPath || activePath.startsWith(itemPath + '/')
}

/** 移动端底部 Tab 栏：固定主目的 + “更多”入口。与桌面侧边栏是完全不同的导航范式。 */
export default function BottomTabBar({
  primary,
  activePath,
  onNavigate,
  onMore,
}: BottomTabBarProps) {
  const { t } = useTranslation('mobile')

  return (
    <nav className="mobile-tabbar" aria-label={t('menu:actions.mainNav')}>
      {primary.map((item) => {
        const Icon = ICONS[item.icon]
        const active = isActive(item.path, activePath)
        return (
          <button
            key={item.path}
            type="button"
            className={`mobile-tabbar__item${active ? ' is-active' : ''}`}
            aria-current={active ? 'page' : undefined}
            onClick={() => onNavigate(item.path)}
          >
            <span className="mobile-tabbar__icon">
              <Icon size={22} />
            </span>
            <span className="mobile-tabbar__label">{t(item.labelKey)}</span>
          </button>
        )
      })}
      <button
        type="button"
        className="mobile-tabbar__item"
        aria-label={t('more')}
        onClick={onMore}
      >
        <span className="mobile-tabbar__icon">
          <svg width={22} height={22} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <circle cx="5" cy="12" r="2" />
            <circle cx="12" cy="12" r="2" />
            <circle cx="19" cy="12" r="2" />
          </svg>
        </span>
        <span className="mobile-tabbar__label">{t('more')}</span>
      </button>
    </nav>
  )
}
