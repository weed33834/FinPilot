import '@testing-library/jest-dom'
import { afterEach, vi } from 'vitest'
import { cleanup } from '@testing-library/react'

// 每个测试后清理 DOM，避免组件泄漏
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

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
