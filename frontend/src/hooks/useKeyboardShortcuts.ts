import { useEffect, useState, useCallback } from 'react'

export interface Shortcut {
  keys: string
  description: string
  action: () => void
}

export interface ShortcutGroup {
  title: string
  items: Omit<Shortcut, 'action'>[]
}

export function useKeyboardShortcuts(shortcuts: Shortcut[]) {
  const [showDialog, setShowDialog] = useState(false)

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't trigger shortcuts when typing in input/textarea/contenteditable
      const target = e.target as HTMLElement
      const isInput =
        target.tagName === 'INPUT' ||
        target.tagName === 'TEXTAREA' ||
        target.isContentEditable ||
        target.getAttribute('role') === 'textbox'

      // '?' always shows dialog, even in inputs when no modifier
      if (e.key === '?' && !e.ctrlKey && !e.metaKey && !e.altKey) {
        if (!isInput) {
          e.preventDefault()
          setShowDialog((v) => !v)
          return
        }
      }

      if (isInput) return

      // Esc closes dialog
      if (e.key === 'Escape') {
        setShowDialog(false)
      }

      // Match shortcuts
      for (const shortcut of shortcuts) {
        const parts = shortcut.keys.toLowerCase().split('+')
        const keyPart = parts[parts.length - 1]
        const hasCtrl = parts.includes('ctrl')
        const hasShift = parts.includes('shift')
        const hasAlt = parts.includes('alt')
        const hasMeta = parts.includes('meta')

        if (
          e.key.toLowerCase() === keyPart &&
          e.ctrlKey === hasCtrl &&
          e.shiftKey === hasShift &&
          e.altKey === hasAlt &&
          e.metaKey === hasMeta
        ) {
          e.preventDefault()
          shortcut.action()
          return
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [shortcuts])

  const closeDialog = useCallback(() => setShowDialog(false), [])
  const toggleDialog = useCallback(() => setShowDialog((v) => !v), [])

  return { showDialog, closeDialog, toggleDialog }
}
