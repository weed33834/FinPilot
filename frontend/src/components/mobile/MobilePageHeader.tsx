import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import '../../i18n/mobile'

interface MobilePageHeaderProps {
  title: string
  onBack?: () => void
  right?: ReactNode
}

/** 移动页头：左侧可选返回 + 标题，右侧操作槽。区别于桌面页内的标题栏。 */
export default function MobilePageHeader({ title, onBack, right }: MobilePageHeaderProps) {
  const { t } = useTranslation('mobile')
  return (
    <header className="mobile-page-header">
      <div className="mobile-page-header__left">
        {onBack && (
          <button
            type="button"
            className="mobile-page-header__back"
            aria-label={t('back')}
            onClick={onBack}
          >
            <svg width={20} height={20} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M15 18l-6-6 6-6" />
            </svg>
          </button>
        )}
        <h1 className="mobile-page-header__title">{title}</h1>
      </div>
      {right && <div className="mobile-page-header__right">{right}</div>}
    </header>
  )
}
