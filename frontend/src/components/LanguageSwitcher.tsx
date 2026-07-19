import { useTranslation } from 'react-i18next'
import { SUPPORTED_LANGUAGES, type LanguageCode } from '../i18n/config.ts'

export default function LanguageSwitcher() {
  const { i18n } = useTranslation()
  const current = i18n.language

  const change = (code: LanguageCode) => {
    void i18n.changeLanguage(code)
  }

  return (
    <div className="lang-switcher" role="group" aria-label={i18n.t('menu:actions.language')}>
      {SUPPORTED_LANGUAGES.map((lang) => (
        <button
          key={lang.code}
          type="button"
          className={current === lang.code ? 'active' : ''}
          onClick={() => change(lang.code)}
          aria-pressed={current === lang.code}
        >
          {lang.label}
        </button>
      ))}
    </div>
  )
}
