import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import zhCNCommon from './locales/zh-CN/common.json'
import zhCNMenu from './locales/zh-CN/menu.json'
import zhCNAuth from './locales/zh-CN/auth.json'
import zhCNDashboard from './locales/zh-CN/dashboard.json'
import enCommon from './locales/en/common.json'
import enMenu from './locales/en/menu.json'
import enAuth from './locales/en/auth.json'
import enDashboard from './locales/en/dashboard.json'

// brand / footer 文案内联在 auth.json 中（登录页专用），通过命名空间映射复用，
// 避免为少量登录页文案单独建立文件。
const zhCNBrand = zhCNAuth.brand
const zhCNFooter = zhCNAuth.footer
const enBrand = enAuth.brand
const enFooter = enAuth.footer

export const SUPPORTED_LANGUAGES = [
  { code: 'zh-CN', label: '中文' },
  { code: 'en', label: 'English' },
] as const

export type LanguageCode = (typeof SUPPORTED_LANGUAGES)[number]['code']

const LANGUAGE_STORAGE_KEY = 'i18nextLng'

function getInitialLanguage(): LanguageCode {
  try {
    const stored = localStorage.getItem(LANGUAGE_STORAGE_KEY)
    if (stored === 'zh-CN' || stored === 'en') return stored
  } catch {
    // localStorage 不可用（隐私模式等）
  }
  return 'zh-CN'
}

i18n
  .use(initReactI18next)
  .init({
    resources: {
      'zh-CN': {
        common: zhCNCommon,
        menu: zhCNMenu,
        auth: zhCNAuth,
        dashboard: zhCNDashboard,
        brand: zhCNBrand,
        footer: zhCNFooter,
      },
      en: {
        common: enCommon,
        menu: enMenu,
        auth: enAuth,
        dashboard: enDashboard,
        brand: enBrand,
        footer: enFooter,
      },
    },
    lng: getInitialLanguage(),
    fallbackLng: 'zh-CN',
    supportedLngs: ['zh-CN', 'en'],
    ns: ['common', 'menu', 'auth', 'dashboard', 'brand', 'footer'],
    defaultNS: 'common',
    interpolation: {
      escapeValue: false,
    },
  })

i18n.on('languageChanged', (lng) => {
  try {
    localStorage.setItem(LANGUAGE_STORAGE_KEY, lng)
  } catch {
    // localStorage 不可用
  }
})

export default i18n
