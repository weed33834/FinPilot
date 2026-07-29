import { useState, useMemo, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import Sidebar from './Sidebar.tsx'
import KeyboardShortcutsDialog from './KeyboardShortcuts.tsx'
import { useKeyboardShortcuts, type ShortcutGroup } from '../hooks/useKeyboardShortcuts'
import { useDevice } from '../context/DeviceContext'
import MobileShell from './mobile/MobileShell'

interface LayoutProps {
  children: ReactNode
}

/** 桌面外壳：原 Sidebar + 主内容 + 快捷键面板，保持桌面行为不变。 */
function DesktopShell({ children }: LayoutProps) {
  const { t } = useTranslation('menu')
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()

  // 快捷键单一数据源：同时驱动注册（action）与帮助面板（description），
  // 避免两处描述分别维护导致不一致。注意：不绑定 ctrl+r（与浏览器刷新冲突）。
  const shortcuts = useMemo(() => [
    { keys: 'ctrl+/', description: t('shortcuts.openAgent'), action: () => navigate('/agent') },
    { keys: 'ctrl+b', description: t('shortcuts.toggleSidebar'), action: () => setOpen((v) => !v) },
    { keys: 'ctrl+d', description: t('shortcuts.gotoDashboard'), action: () => navigate('/dashboard') },
    { keys: 'ctrl+e', description: t('shortcuts.gotoDocuments'), action: () => navigate('/documents') },
    { keys: 'ctrl+g', description: t('shortcuts.gotoReports'), action: () => navigate('/reports') },
  ], [navigate, t])

  const { showDialog, closeDialog } = useKeyboardShortcuts(shortcuts)

  // 帮助面板分组：导航项从 shortcuts 派生，界面项为静态约定
  const shortcutGroups: ShortcutGroup[] = useMemo(() => [
    {
      title: t('shortcuts.groupNavigation'),
      items: shortcuts.map((s) => ({
        keys: s.keys.replace('ctrl', 'Ctrl').replace('+', '+').toUpperCase(),
        description: s.description,
      })),
    },
    {
      title: t('shortcuts.groupInterface'),
      items: [
        { keys: '?', description: t('shortcuts.showHelp') },
        { keys: 'Esc', description: t('shortcuts.closeDialog') },
      ],
    },
  ], [shortcuts, t])

  return (
    <div className="app-layout">
      <Sidebar open={open} onToggle={() => setOpen((v) => !v)} onClose={() => setOpen(false)} />
      <main className="main-content">{children}</main>
      <KeyboardShortcutsDialog open={showDialog} onClose={closeDialog} groups={shortcutGroups} />
    </div>
  )
}

/**
 * 布局分发器：移动端走独立 MobileShell（底部 Tab + 顶栏），桌面端走原 Sidebar 布局。
 * 两端共用同一路由与页面组件，深链通用；互不污染。
 */
export default function Layout({ children }: LayoutProps) {
  const { isMobile } = useDevice()
  return isMobile ? <MobileShell>{children}</MobileShell> : <DesktopShell>{children}</DesktopShell>
}
