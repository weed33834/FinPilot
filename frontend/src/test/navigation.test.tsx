import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, waitFor, fireEvent } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from '../App'
import { DeviceProvider } from '../context/DeviceContext'
import { useAuthStore } from '../stores/authStore'

// Sentry 在 jsdom 下无意义，且可能初始化失败，mock 掉
vi.mock('../observability', () => ({
  captureException: vi.fn(),
  setupSentry: vi.fn(),
  captureMessage: vi.fn(),
  setUserContext: vi.fn(),
  clearUserContext: vi.fn(),
}))

// mock 后端请求：让 /auth/me 成功返回 admin（清除 loading 门禁），其余返回空数据，
// 使页面在 jsdom 下真实渲染，从而能测试导航切换（无需真实后端）
vi.mock('../api/client', () => {
  const api = {
    get: vi.fn(async (url: string) => {
      if (url === '/auth/me') {
        return { data: { code: 0, message: 'ok', data: { id: '1', role: 'admin', username: 'Tester' } } }
      }
      return { data: { code: 0, message: 'ok', data: {} } }
    }),
    post: vi.fn(async () => ({ data: { code: 0, message: 'ok', data: {} } })),
    put: vi.fn(async () => ({ data: { code: 0, message: 'ok', data: {} } })),
    delete: vi.fn(async () => ({ data: { code: 0, message: 'ok', data: {} } })),
    patch: vi.fn(async () => ({ data: { code: 0, message: 'ok', data: {} } })),
  }
  return { api }
})

// recharts 等依赖 ResizeObserver，jsdom 不实现，提供兜底
class RO {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver = RO

// recharts 在 jsdom 下导入/渲染异常，mock 为透传占位，使真实页面模块可在 jsdom 解析
vi.mock('recharts', () => {
  const C = ({ children }: { children?: unknown }) => children as never
  return {
    BarChart: C,
    Bar: C,
    CartesianGrid: C,
    PieChart: C,
    Pie: C,
    Cell: C,
    ResponsiveContainer: C,
    Tooltip: C,
    XAxis: C,
    YAxis: C,
    LineChart: C,
    Line: C,
    AreaChart: C,
    Area: C,
    Legend: C,
    RadarChart: C,
    Radar: C,
    ScatterChart: C,
    Scatter: C,
  }
})

function seedLogin() {
  useAuthStore.setState({
    username: 'Tester',
    role: 'admin',
    isAuthenticated: true,
    loading: false,
    logout: vi.fn(),
  })
}

function renderAt(path: string) {
  // BrowserRouter 读取 window.location，预先设置初始路径
  window.history.replaceState(null, '', path)
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0 },
      mutations: { retry: false },
    },
  })
  return render(
    <QueryClientProvider client={client}>
      <BrowserRouter>
        <DeviceProvider>
          <App />
        </DeviceProvider>
      </BrowserRouter>
    </QueryClientProvider>,
  )
}

/** 读取主内容区第一个 h1 的文本（页面标题），用于判定内容是否切换 */
function mainH1(): string | null {
  const el = document.querySelector('main h1')
  return el ? el.textContent : null
}

describe('导航：点击侧边栏后 URL 与页面内容同步切换', () => {
  beforeEach(() => {
    seedLogin()
  })

  const targets = [
    '/agent',
    '/documents',
    '/reports',
    '/queries',
    '/conversations',
    '/kpi',
    '/audit',
    '/security',
    '/admin/models',
  ]

  it('初始仪表盘渲染且处于 /dashboard', async () => {
    renderAt('/dashboard')
    await waitFor(() => expect(mainH1()).not.toBeNull())
    expect(window.location.pathname).toBe('/dashboard')
  })

  for (const target of targets) {
    it(`从 /dashboard 点击侧边栏跳转到 ${target}：URL 与内容均切换`, async () => {
      const { container } = renderAt('/dashboard')

      // 等待看板（原界面）渲染
      await waitFor(() => expect(mainH1()).not.toBeNull())
      const h1Before = mainH1()
      expect(window.location.pathname).toBe('/dashboard')

      // 找到侧边栏中指向目标路径的链接并点击
      const link = container.querySelector(
        `a.sidebar-link[href="${target}"], a.sidebar-link-child[href="${target}"]`,
      ) as HTMLAnchorElement | null
      expect(link, `侧边栏应包含指向 ${target} 的链接`).toBeTruthy()

      fireEvent.click(link!)

      // 1) URL（路由）应变化
      await waitFor(
        () => expect(window.location.pathname).toBe(target),
        { timeout: 10000 },
      )

      // 2) 页面内容应更新：主标题不再是原看板标题
      await waitFor(
        () => {
          const h1After = mainH1()
          expect(h1After).not.toBeNull()
          expect(h1After).not.toBe(h1Before)
        },
        { timeout: 10000 },
      )
    })
  }

  it('连续点击多个导航：每一步 URL 与内容都正确切换', async () => {
    const { container } = renderAt('/dashboard')
    await waitFor(() => expect(mainH1()).not.toBeNull())

    const chain = ['/agent', '/documents', '/reports', '/queries']
    let prevH1 = mainH1()
    for (const target of chain) {
      const link = container.querySelector(
        `a.sidebar-link[href="${target}"], a.sidebar-link-child[href="${target}"]`,
      ) as HTMLAnchorElement | null
      expect(link, `侧边栏应包含指向 ${target} 的链接`).toBeTruthy()
      fireEvent.click(link!)

      await waitFor(() => expect(window.location.pathname).toBe(target), { timeout: 10000 })
      await waitFor(
        () => {
          const h1 = mainH1()
          expect(h1).not.toBeNull()
          expect(h1).not.toBe(prevH1)
        },
        { timeout: 10000 },
      )
      prevH1 = mainH1()
    }
  })
})
