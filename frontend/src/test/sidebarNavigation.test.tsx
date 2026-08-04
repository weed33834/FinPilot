import { describe, it, expect, beforeEach } from 'vitest'
import { screen, fireEvent } from '@testing-library/react'
import { Routes, Route } from 'react-router-dom'
import i18n from '../i18n/config'
import { renderWithProviders, seedAuth, mockMatchMedia } from './renderWithProviders'
import Sidebar from '../components/Sidebar'

beforeEach(() => {
  // admin 角色可看到全部菜单（含分组）；桌面端走 Sidebar 主路径
  seedAuth({ role: 'admin' })
  mockMatchMedia(false)
  void i18n.changeLanguage('zh-CN')
})

describe('Sidebar 导航与渲染稳定性', () => {
  it('渲染不触发无限重渲染（回归：sections 未 memo 导致的 Maximum update depth）', () => {
    // 若回归，Sidebar 的自动展开 effect 会陷入「新 sections 引用 -> setExpanded 新 Set -> 重渲染」死循环，
    // React 会抛出 Maximum update depth 并使本测试失败。能正常渲染并找到菜单即说明循环已消除。
    renderWithProviders(<Sidebar open onToggle={() => {}} onClose={() => {}} />)
    expect(screen.getByText('智能对话')).toBeInTheDocument()
    expect(screen.getByText('文档管理')).toBeInTheDocument()
  })

  it('点击侧边栏菜单后路由与渲染内容同步切换', () => {
    function Harness() {
      return (
        <>
          <Sidebar open onToggle={() => {}} onClose={() => {}} />
          <Routes>
            <Route path="/dashboard" element={<div data-testid="page">PAGE:/dashboard</div>} />
            <Route path="/documents" element={<div data-testid="page">PAGE:/documents</div>} />
            <Route path="/reports" element={<div data-testid="page">PAGE:/reports</div>} />
          </Routes>
        </>
      )
    }
    renderWithProviders(<Harness />, { route: '/dashboard' })
    expect(screen.getByTestId('page').textContent).toBe('PAGE:/dashboard')

    // 依次点击不同导航按钮，URL 与内容应同步切换
    fireEvent.click(screen.getByText('文档管理'))
    expect(screen.getByTestId('page').textContent).toBe('PAGE:/documents')

    fireEvent.click(screen.getByText('财务报告'))
    expect(screen.getByTestId('page').textContent).toBe('PAGE:/reports')
  })

  it('路由处于子项路径时自动展开其所属分组', () => {
    // /users 属于「用户与权限」分组（/admin/users-group），进入该路由应自动展开该分组
    renderWithProviders(<Sidebar open onToggle={() => {}} onClose={() => {}} />, { route: '/users' })
    const header = screen.getByText('用户与权限')
    const group = header.closest('.sidebar-nav-group')
    expect(group?.className).toContain('expanded')
  })
})
