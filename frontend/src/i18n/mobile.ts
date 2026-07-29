import i18n from './config.ts'
import enResource from './locales/en/mobile.json'
import zhCnResource from './locales/zh-CN/mobile.json'

// 移动端专属文案命名空间，沿用 agent-chat 的“模块内注入 bundle”模式，
// 不改动 i18n/config.ts 全局注册表。
const NS = 'mobile'
if (!i18n.hasResourceBundle('en', NS)) {
  i18n.addResourceBundle('en', NS, enResource)
}
if (!i18n.hasResourceBundle('zh-CN', NS)) {
  i18n.addResourceBundle('zh-CN', NS, zhCnResource)
}

export default NS
