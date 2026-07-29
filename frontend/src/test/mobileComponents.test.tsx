import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { I18nextProvider } from 'react-i18next'
import i18n from '../i18n/config'
import { renderWithProviders, seedAuth, mockMatchMedia } from './renderWithProviders'
import BottomTabBar from '../components/mobile/BottomTabBar'
import BottomSheet from '../components/mobile/BottomSheet'
import MobilePageHeader from '../components/mobile/MobilePageHeader'
import MobileCard from '../components/mobile/MobileCard'
import MobileDesktopRequired from '../components/mobile/MobileDesktopRequired'
import type { NavItem } from '../utils/navigation'

const primary: NavItem[] = [
  { path: '/agent', labelKey: 'menu:items.agent', icon: 'agent' },
  { path: '/dashboard', labelKey: 'menu:items.dashboard', icon: 'dashboard' },
  { path: '/documents', labelKey: 'menu:items.documents', icon: 'documents' },
  { path: '/reports', labelKey: 'menu:items.reports', icon: 'reports' },
]

beforeEach(() => {
  seedAuth()
  mockMatchMedia(true)
  void i18n.changeLanguage('zh-CN')
})

describe('BottomTabBar', () => {
  it('渲染 4 个主入口与「更多」按钮', () => {
    const onNavigate = vi.fn()
    const onMore = vi.fn()
    renderWithProviders(
      <BottomTabBar primary={primary} activePath="/dashboard" onNavigate={onNavigate} onMore={onMore} />,
    )
    expect(screen.getByText('数据看板').textContent).toBeTruthy()
    expect(screen.getByText('更多')).toBeInTheDocument()
  })

  it('点击 Tab 触发 onNavigate，点击更多触发 onMore', () => {
    const onNavigate = vi.fn()
    const onMore = vi.fn()
    renderWithProviders(
      <BottomTabBar primary={primary} activePath="/dashboard" onNavigate={onNavigate} onMore={onMore} />,
    )
    fireEvent.click(screen.getByText('文档管理'))
    expect(onNavigate).toHaveBeenCalledWith('/documents')
    fireEvent.click(screen.getByText('更多'))
    expect(onMore).toHaveBeenCalledTimes(1)
  })
})

describe('BottomSheet', () => {
  it('打开时渲染标题与内容，点击遮罩关闭', () => {
    const onClose = vi.fn()
    renderWithProviders(
      <BottomSheet open onClose={onClose} title="测试弹层">
        <div>子内容</div>
      </BottomSheet>,
    )
    expect(screen.getByText('测试弹层')).toBeInTheDocument()
    expect(screen.getByText('子内容')).toBeInTheDocument()
    fireEvent.click(document.querySelector('.mobile-sheet__overlay') as Element)
    expect(onClose).toHaveBeenCalled()
  })

  it('关闭时不渲染内容', () => {
    renderWithProviders(
      <BottomSheet open={false} onClose={() => {}} title="测试弹层">
        <div>子内容</div>
      </BottomSheet>,
    )
    expect(screen.queryByText('子内容')).not.toBeInTheDocument()
  })
})

describe('MobilePageHeader', () => {
  it('渲染标题，点击返回触发 onBack', () => {
    const onBack = vi.fn()
    renderWithProviders(<MobilePageHeader title="详情" onBack={onBack} />)
    expect(screen.getByText('详情')).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('返回'))
    expect(onBack).toHaveBeenCalledTimes(1)
  })
})

describe('MobileCard', () => {
  it('可点击卡片触发 onClick', () => {
    const onClick = vi.fn()
    renderWithProviders(
      <MobileCard onClick={onClick}>卡片内容</MobileCard>,
    )
    fireEvent.click(screen.getByText('卡片内容'))
    expect(onClick).toHaveBeenCalledTimes(1)
  })
})

describe('MobileDesktopRequired', () => {
  it('渲染桌面端提示，点击按钮跳转工作台', async () => {
    render(
      <I18nextProvider i18n={i18n}>
        <MemoryRouter initialEntries={['/users']}>
          <Routes>
            <Route path="/users" element={<MobileDesktopRequired />} />
            <Route path="/dashboard" element={<div>dashboard-marker</div>} />
          </Routes>
        </MemoryRouter>
      </I18nextProvider>,
    )
    expect(screen.getByText('建议在桌面端使用')).toBeInTheDocument()
    fireEvent.click(screen.getByText('返回工作台'))
    await waitFor(() => expect(screen.getByText('dashboard-marker')).toBeInTheDocument())
  })
})
