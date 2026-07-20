/**
 * 斜杠命令面板 — 用户在输入框输入 / 时弹出，过滤并展示可用命令。
 *
 * - 按当前用户角色过滤命令
 * - 支持模糊搜索（命令名 + 描述）
 * - 键盘上下选择 + Enter 确认 + Esc 关闭
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import {
  getCommandsForRole,
  type SlashCommand,
  type CommandCategory,
} from '../utils/slashCommands'

interface Props {
  role: string | null
  query: string
  onSelect: (command: SlashCommand) => void
  onClose: () => void
}

const CATEGORY_LABELS: Record<CommandCategory, string> = {
  help: '帮助',
  data: '数据查询',
  report: '研报',
  analysis: '分析工具',
  admin: '管理（仅管理员）',
  system: '系统',
}

const CATEGORY_ORDER: CommandCategory[] = ['help', 'data', 'report', 'analysis', 'system', 'admin']

export default function SlashCommandPalette({ role, query, onSelect, onClose }: Props) {
  const allCommands = useMemo(() => getCommandsForRole(role), [role])
  const [selectedIndex, setSelectedIndex] = useState(0)
  const listRef = useRef<HTMLDivElement>(null)

  // 去掉前导 / 后的搜索词
  const searchTerm = query.trim().replace(/^\//, '').toLowerCase()

  const filtered = useMemo(() => {
    if (!searchTerm) return allCommands
    return allCommands.filter((c) => {
      return (
        c.name.toLowerCase().includes(searchTerm) ||
        c.description.toLowerCase().includes(searchTerm) ||
        c.usage.toLowerCase().includes(searchTerm)
      )
    })
  }, [allCommands, searchTerm])

  // 按分类分组
  const grouped = useMemo(() => {
    const map = new Map<CommandCategory, SlashCommand[]>()
    filtered.forEach((c) => {
      if (!map.has(c.category)) map.set(c.category, [])
      map.get(c.category)!.push(c)
    })
    return Array.from(map.entries())
      .sort(([a], [b]) => CATEGORY_ORDER.indexOf(a) - CATEGORY_ORDER.indexOf(b))
  }, [filtered])

  // 平铺的命令列表（用于键盘导航）
  const flatList = useMemo(() => grouped.flatMap(([, items]) => items), [grouped])

  useEffect(() => {
    setSelectedIndex(0)
  }, [searchTerm])

  // 滚动选中项到可见区域
  useEffect(() => {
    const el = listRef.current?.querySelector<HTMLElement>(`[data-idx="${selectedIndex}"]`)
    el?.scrollIntoView({ block: 'nearest' })
  }, [selectedIndex])

  // 键盘事件由父组件透传，这里只处理选择
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setSelectedIndex((i) => Math.min(i + 1, flatList.length - 1))
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        setSelectedIndex((i) => Math.max(i - 1, 0))
      } else if (e.key === 'Enter') {
        // 仅当面板可见时拦截 Enter
        if (flatList[selectedIndex]) {
          e.preventDefault()
          e.stopPropagation()
          onSelect(flatList[selectedIndex])
        }
      } else if (e.key === 'Escape') {
        e.preventDefault()
        onClose()
      }
    }
    document.addEventListener('keydown', handler, true)
    return () => document.removeEventListener('keydown', handler, true)
  }, [flatList, selectedIndex, onSelect, onClose])

  if (!flatList.length) {
    return (
      <div className="slash-palette">
        <div className="slash-palette-empty">
          没有匹配的命令 — 输入 <code>/help</code> 查看可用命令
        </div>
      </div>
    )
  }

  let runningIdx = -1

  return (
    <div className="slash-palette" ref={listRef}>
      <div className="slash-palette-header">
        <span className="slash-palette-title">命令面板</span>
        <span className="slash-palette-hint">
          <kbd>↑↓</kbd> 选择 · <kbd>Enter</kbd> 执行 · <kbd>Esc</kbd> 关闭
        </span>
      </div>
      <div className="slash-palette-list">
        {grouped.map(([cat, items]) => (
          <div key={cat} className="slash-palette-group">
            <div className="slash-palette-group-label">{CATEGORY_LABELS[cat]}</div>
            {items.map((cmd) => {
              runningIdx++
              const idx = runningIdx
              const selected = idx === selectedIndex
              return (
                <button
                  key={cmd.name}
                  type="button"
                  data-idx={idx}
                  className={`slash-palette-item ${selected ? 'selected' : ''} role-${cmd.role}`}
                  onMouseEnter={() => setSelectedIndex(idx)}
                  onClick={() => onSelect(cmd)}
                >
                  <div className="slash-palette-item-main">
                    <span className="slash-palette-item-usage">/{cmd.usage}</span>
                    {cmd.role === 'admin' && (
                      <span className="slash-palette-item-badge">管理员</span>
                    )}
                  </div>
                  <div className="slash-palette-item-desc">{cmd.description}</div>
                </button>
              )
            })}
          </div>
        ))}
      </div>
    </div>
  )
}
