import type { ReactElement } from 'react'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { I18nextProvider } from 'react-i18next'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { vi } from 'vitest'
import i18n from '../i18n/config'
import { DeviceProvider } from '../context/DeviceContext'
import { useAuthStore } from '../stores/authStore'

/** 控制 matchMedia 返回值，用于切换移动/桌面。 */
export function mockMatchMedia(matches: boolean) {
  window.matchMedia = (query: string) =>
    ({
      matches,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList
}

/** 提供一个最小登录态，避免外壳读取 undefined 报错。 */
export function seedAuth(overrides: Record<string, unknown> = {}) {
  useAuthStore.setState({
    username: 'Tester',
    role: 'admin',
    isAuthenticated: true,
    loading: false,
    logout: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  })
}

interface Options {
  route?: string
}

/**
 * 统一渲染包裹：i18n + react-query + MemoryRouter + DeviceProvider。
 * 移动端组件可能用到导航/翻译/查询，统一提供，减少重复样板。
 */
export function renderWithProviders(ui: ReactElement, { route = '/' }: Options = {}) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0 },
      mutations: { retry: false },
    },
  })
  return render(
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[route]}>
          <DeviceProvider>{ui}</DeviceProvider>
        </MemoryRouter>
      </QueryClientProvider>
    </I18nextProvider>,
  )
}
