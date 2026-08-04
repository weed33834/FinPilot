import '@testing-library/jest-dom'
import { afterEach, vi } from 'vitest'
import { cleanup } from '@testing-library/react'

// 每个测试后清理 DOM，避免组件泄漏
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

// jsdom 未实现 Element.prototype.scrollIntoView（真实浏览器有）。
// 组件中的自动滚动逻辑（如 AgentChatPage 消息跟随滚动）在 effect 里调用它，
// 缺失时会抛 TypeError 并被 ErrorBoundary 捕获，导致页面渲染成错误卡片、测试误判。
// 用普通函数而非 vi.fn() 赋值：afterEach 的 restoreAllMocks 不会将其移除。
if (typeof Element !== 'undefined' && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = function scrollIntoViewPolyfill() {}
}

// jsdom 不实现 matchMedia，提供安全默认实现；具体用例可用 mockMatchMedia 覆盖
if (typeof window !== 'undefined' && !window.matchMedia) {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList
}
