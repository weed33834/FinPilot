import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { renderWithProviders, mockMatchMedia } from './renderWithProviders'
import Layout from '../components/Layout'

// 外壳内部依赖较重（侧边栏/通知等），此处用轻量标记替身，
// 仅验证 Layout 按设备模式在「桌面外壳 / 移动外壳」之间正确分发。
vi.mock('../components/Sidebar', () => ({
  default: ({ children }: { children: ReactNode }) => (
    <div data-testid="desktop-shell">{children}</div>
  ),
}))
vi.mock('../components/mobile/MobileShell', () => ({
  default: ({ children }: { children: ReactNode }) => (
    <div data-testid="mobile-shell">{children}</div>
  ),
}))

beforeEach(() => {
  mockMatchMedia(false)
})

describe('Layout 设备分发', () => {
  it('桌面端分发到桌面外壳（非移动外壳）', () => {
    mockMatchMedia(false)
    renderWithProviders(<Layout><div data-testid="child">内容</div></Layout>, {
      route: '/dashboard',
    })
    expect(screen.getByTestId('desktop-shell')).toBeInTheDocument()
    expect(screen.queryByTestId('mobile-shell')).not.toBeInTheDocument()
    expect(screen.getByTestId('child')).toBeInTheDocument()
  })

  it('移动端分发到移动外壳（非桌面外壳）', () => {
    mockMatchMedia(true)
    renderWithProviders(<Layout><div data-testid="child">内容</div></Layout>, {
      route: '/dashboard',
    })
    expect(screen.getByTestId('mobile-shell')).toBeInTheDocument()
    expect(screen.queryByTestId('desktop-shell')).not.toBeInTheDocument()
    expect(screen.getByTestId('child')).toBeInTheDocument()
  })
})
