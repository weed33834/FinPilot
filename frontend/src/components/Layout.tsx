import { useState, type ReactNode } from 'react'
import Sidebar from './Sidebar.tsx'

interface LayoutProps {
  children: ReactNode
}

export default function Layout({ children }: LayoutProps) {
  const [open, setOpen] = useState(false)
  return (
    <div className="app-layout">
      <Sidebar open={open} onToggle={() => setOpen((v) => !v)} onClose={() => setOpen(false)} />
      <main className="main-content">{children}</main>
    </div>
  )
}
