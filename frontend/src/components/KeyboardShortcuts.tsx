import { useEffect, useRef } from 'react'
import { ICONS } from './ui/Icons'
import type { ShortcutGroup } from '../hooks/useKeyboardShortcuts'

interface KeyboardShortcutsDialogProps {
  open: boolean
  onClose: () => void
  groups: ShortcutGroup[]
}

export default function KeyboardShortcutsDialog({
  open,
  onClose,
  groups,
}: KeyboardShortcutsDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const el = dialogRef.current
    if (!el) return
    if (open && !el.open) {
      el.showModal()
    } else if (!open && el.open) {
      el.close()
    }
  }, [open])

  if (!open) return null

  return (
    <dialog
      ref={dialogRef}
      className="shortcuts-dialog"
      onClick={(e) => {
        if (e.target === dialogRef.current) onClose()
      }}
      onClose={onClose}
    >
      <div className="shortcuts-header">
        <h2>键盘快捷键</h2>
        <button className="shortcuts-close" onClick={onClose} aria-label="关闭">
          <ICONS.close size={18} />
        </button>
      </div>
      <div className="shortcuts-body">
        {groups.map((group) => (
          <div key={group.title} className="shortcuts-group">
            <h3 className="shortcuts-group-title">{group.title}</h3>
            <div className="shortcuts-list">
              {group.items.map((item) => (
                <div key={item.keys + item.description} className="shortcut-row">
                  <kbd className="shortcut-keys">
                    {item.keys.split('+').map((key, i) => (
                      <span key={i}>
                        {i > 0 && <span className="shortcut-plus">+</span>}
                        <span className="shortcut-key">{key.toUpperCase()}</span>
                      </span>
                    ))}
                  </kbd>
                  <span className="shortcut-desc">{item.description}</span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
      <div className="shortcuts-footer">
        <small>按 <kbd>?</kbd> 随时查看快捷键</small>
      </div>
    </dialog>
  )
}
