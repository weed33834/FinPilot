import { useTranslation } from 'react-i18next'
import { ICONS } from '../ui/Icons'
import '../../i18n/mobile'

/** 桌面优先提示横幅：管理类页面在移动端单栏降级展示时给出引导。 */
export default function MobileNotice() {
  const { t } = useTranslation('mobile')
  return (
    <div className="mobile-notice" role="status">
      <span className="mobile-notice__icon">
        <ICONS.security size={16} />
      </span>
      <div className="mobile-notice__text">
        <div className="mobile-notice__title">{t('desktopRecommended')}</div>
        <div className="mobile-notice__hint">{t('desktopRecommendedHint')}</div>
      </div>
    </div>
  )
}
