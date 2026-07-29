import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ICONS } from '../ui/Icons'
import '../../i18n/mobile'

/**
 * 移动端「建议在桌面端使用」整页提示，用于管理/配置类与暂未做移动端独立设计的页面。
 * 由 PrivateRoute 的集中式守卫按路径分发；不在移动端为这些页面单独重设计，
 * 避免把复杂的后台表格强行塞进小屏。
 */
export default function MobileDesktopRequired() {
  const { t } = useTranslation(['mobile'])
  const navigate = useNavigate()

  return (
    <div className="mdesktop-required">
      <div className="mdesktop-required__icon">
        <ICONS.settings size={40} />
      </div>
      <h2 className="mdesktop-required__title">{t('mobile:desktopRecommended')}</h2>
      <p className="mdesktop-required__hint">{t('mobile:desktopRecommendedHint')}</p>
      <button
        type="button"
        className="mdesktop-required__btn"
        onClick={() => navigate('/dashboard')}
      >
        {t('mobile:backToWorkspace')}
      </button>
    </div>
  )
}
