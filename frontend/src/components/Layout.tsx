import { useState, useMemo, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import Sidebar from './Sidebar.tsx'
import KeyboardShortcutsDialog from './KeyboardShortcuts.tsx'
import { useKeyboardShortcuts, type ShortcutGroup } from '../hooks/useKeyboardShortcuts'

interface LayoutProps {
  children: ReactNode
}

export default function Layout({ children }: LayoutProps) {
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()

  const shortcuts = useMemo(() => [
    { keys: 'ctrl+/', description: '打开智能对话', action: () => navigate('/agent') },
    { keys: 'ctrl+b', description: '切换侧边栏', action: () => setOpen((v) => !v) },
    { keys: 'ctrl+d', description: '跳转数据看板', action: () => navigate('/dashboard') },
    { keys: 'ctrl+e', description: '跳转文档管理', action: () => navigate('/documents') },
    { keys: 'ctrl+r', description: '跳转财务报告', action: () => navigate('/reports') },
  ], [navigate])

  const { showDialog, closeDialog } = useKeyboardShortcuts(shortcuts)

  const shortcutGroups: ShortcutGroup[] = useMemo(() => [
    {
      title: '导航',
      items: [
        { keys: 'Ctrl+/', description: '打开智能对话' },
        { keys: 'Ctrl+D', description: '跳转数据看板' },
        { keys: 'Ctrl+E', description: '跳转文档管理' },
        { keys: 'Ctrl+R', description: '跳转财务报告' },
      ],
    },
    {
      title: '界面',
      items: [
        { keys: 'Ctrl+B', description: '切换侧边栏' },
        { keys: '?', description: '显示/隐藏快捷键帮助' },
        { keys: 'Esc', description: '关闭弹窗' },
      ],
    },
  ], [])

  return (
    <div className="app-layout">
      <Sidebar open={open} onToggle={() => setOpen((v) => !v)} onClose={() => setOpen(false)} />
      <main className="main-content">{children}</main>
      <KeyboardShortcutsDialog open={showDialog} onClose={closeDialog} groups={shortcutGroups} />
    </div>
  )
}
