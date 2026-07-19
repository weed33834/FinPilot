import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import EmptyState from '../../components/ui/EmptyState.tsx'
import { ICONS } from '../../components/ui/Icons.tsx'

interface PaletteItem {
  type: string
  label: string
  color: string
}

interface WFNode {
  id: string
  type: string
  name: string
  description: string
  params: string
  x: number
  y: number
}

interface WFEdge {
  id: string
  source: string
  target: string
}

interface DragState {
  id: string
  offsetX: number
  offsetY: number
  startClientX: number
  startClientY: number
  moved: boolean
}

const PALETTE: PaletteItem[] = [
  { type: 'llm', label: 'LLM调用', color: '#6366f1' },
  { type: 'query', label: '数据查询', color: '#0ea5e9' },
  { type: 'tool', label: '工具执行', color: '#10b981' },
  { type: 'condition', label: '条件判断', color: '#f59e0b' },
  { type: 'output', label: '输出', color: '#8b5cf6' },
  { type: 'start', label: '开始', color: '#22c55e' },
  { type: 'end', label: '结束', color: '#ef4444' },
]

const NODE_W = 150
const NODE_H = 56
const CANVAS_W = 2200
const CANVAS_H = 1500
const STORAGE_KEY = 'workflow-editor-state'
const DRAG_THRESHOLD = 4

function uid(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

function paletteOf(type: string): PaletteItem {
  return PALETTE.find((p) => p.type === type) ?? PALETTE[0]
}

function nodeLeft(n: WFNode) {
  return { x: n.x, y: n.y + NODE_H / 2 }
}
function nodeRight(n: WFNode) {
  return { x: n.x + NODE_W, y: n.y + NODE_H / 2 }
}

export default function WorkflowEditorPage() {
  const [nodes, setNodes] = useState<WFNode[]>([])
  const [edges, setEdges] = useState<WFEdge[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [connectSource, setConnectSource] = useState<string | null>(null)
  const [mousePos, setMousePos] = useState<{ x: number; y: number } | null>(null)
  const [notice, setNotice] = useState('')

  const innerRef = useRef<HTMLDivElement | null>(null)
  const dragRef = useRef<DragState | null>(null)
  const connectSourceRef = useRef<string | null>(null)

  useEffect(() => {
    connectSourceRef.current = connectSource
  }, [connectSource])

  // 自动消失的提示
  useEffect(() => {
    if (!notice) return
    const t = window.setTimeout(() => setNotice(''), 2200)
    return () => window.clearTimeout(t)
  }, [notice])

  const handleNodeClick = useCallback((id: string) => {
    setSelectedId(id)
    const src = connectSourceRef.current
    if (src === null) {
      setConnectSource(id)
    } else if (src === id) {
      setConnectSource(null)
    } else {
      setEdges((prev) => {
        if (prev.some((e) => e.source === src && e.target === id)) return prev
        return [...prev, { id: uid(), source: src, target: id }]
      })
      setConnectSource(null)
    }
  }, [])

  // 全局拖拽 / 预览线监听（挂载一次）
  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      const drag = dragRef.current
      if (drag) {
        const dx = e.clientX - drag.startClientX
        const dy = e.clientY - drag.startClientY
        if (!drag.moved && Math.hypot(dx, dy) > DRAG_THRESHOLD) {
          drag.moved = true
        }
        if (drag.moved && innerRef.current) {
          const rect = innerRef.current.getBoundingClientRect()
          const contentX = e.clientX - rect.left
          const contentY = e.clientY - rect.top
          const nx = Math.max(0, contentX - drag.offsetX)
          const ny = Math.max(0, contentY - drag.offsetY)
          setNodes((prev) =>
            prev.map((n) => (n.id === drag.id ? { ...n, x: nx, y: ny } : n)),
          )
        }
      }
      if (connectSourceRef.current && innerRef.current) {
        const rect = innerRef.current.getBoundingClientRect()
        setMousePos({ x: e.clientX - rect.left, y: e.clientY - rect.top })
      }
    }
    const onUp = () => {
      const drag = dragRef.current
      if (drag && !drag.moved) {
        handleNodeClick(drag.id)
      }
      dragRef.current = null
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [handleNodeClick])

  const deleteNode = useCallback((id: string) => {
    setNodes((prev) => prev.filter((n) => n.id !== id))
    setEdges((prev) => prev.filter((e) => e.source !== id && e.target !== id))
    setSelectedId((prev) => (prev === id ? null : prev))
    setConnectSource((prev) => (prev === id ? null : prev))
  }, [])

  // 键盘：Delete 删除选中 / Esc 取消
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setSelectedId(null)
        setConnectSource(null)
        return
      }
      if ((e.key === 'Delete' || e.key === 'Backspace') && selectedId) {
        const el = document.activeElement
        const tag = el?.tagName
        if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
        e.preventDefault()
        deleteNode(selectedId)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [selectedId, deleteNode])

  const addNode = useCallback((item: PaletteItem) => {
    const id = uid()
    setNodes((prev) => {
      const count = prev.length
      const x = 240 + (count % 6) * 36
      const y = 110 + (count % 6) * 36
      return [
        ...prev,
        {
          id,
          type: item.type,
          name: item.label,
          description: '',
          params: '{}',
          x,
          y,
        },
      ]
    })
    setSelectedId(id)
    setConnectSource(null)
  }, [])

  const onNodeMouseDown = (e: React.MouseEvent, node: WFNode) => {
    e.preventDefault()
    e.stopPropagation()
    if (!innerRef.current) return
    const rect = innerRef.current.getBoundingClientRect()
    const contentX = e.clientX - rect.left
    const contentY = e.clientY - rect.top
    dragRef.current = {
      id: node.id,
      offsetX: contentX - node.x,
      offsetY: contentY - node.y,
      startClientX: e.clientX,
      startClientY: e.clientY,
      moved: false,
    }
  }

  const onCanvasMouseDown = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      setSelectedId(null)
      setConnectSource(null)
    }
  }

  const deleteEdge = (id: string) => {
    setEdges((prev) => prev.filter((e) => e.id !== id))
  }

  const updateNode = (id: string, patch: Partial<WFNode>) => {
    setNodes((prev) => prev.map((n) => (n.id === id ? { ...n, ...patch } : n)))
  }

  const exportJSON = () => {
    const payload = { nodes, edges }
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'workflow.json'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    setNotice('已导出 workflow.json')
  }

  const saveLocal = () => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ nodes, edges }))
      setNotice('已保存到本地存储')
    } catch {
      setNotice('保存失败')
    }
  }

  const loadLocal = () => {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) {
      setNotice('本地无保存数据')
      return
    }
    try {
      const parsed = JSON.parse(raw) as { nodes?: WFNode[]; edges?: WFEdge[] }
      setNodes(parsed.nodes ?? [])
      setEdges(parsed.edges ?? [])
      setSelectedId(null)
      setConnectSource(null)
      setNotice('已从本地加载')
    } catch {
      setNotice('本地数据解析失败')
    }
  }

  const clearAll = () => {
    setNodes([])
    setEdges([])
    setSelectedId(null)
    setConnectSource(null)
    setNotice('已清空画布')
  }

  const selectedNode = useMemo(
    () => nodes.find((n) => n.id === selectedId) ?? null,
    [nodes, selectedId],
  )

  const sourceNode = useMemo(
    () => (connectSource ? nodes.find((n) => n.id === connectSource) ?? null : null),
    [nodes, connectSource],
  )

  const nodeById = useMemo(() => {
    const m = new Map<string, WFNode>()
    for (const n of nodes) m.set(n.id, n)
    return m
  }, [nodes])

  const edgePaths = useMemo(() => {
    return edges
      .map((e) => {
        const s = nodeById.get(e.source)
        const t = nodeById.get(e.target)
        if (!s || !t) return null
        const sp = nodeRight(s)
        const tp = nodeLeft(t)
        return {
          id: e.id,
          d: `M ${sp.x} ${sp.y} C ${sp.x + 50} ${sp.y}, ${tp.x - 50} ${tp.y}, ${tp.x} ${tp.y}`,
        }
      })
      .filter(Boolean) as Array<{ id: string; d: string }>
  }, [edges, nodeById])

  const previewPath = useMemo(() => {
    if (!sourceNode || !mousePos) return null
    const sp = nodeRight(sourceNode)
    return `M ${sp.x} ${sp.y} L ${mousePos.x} ${mousePos.y}`
  }, [sourceNode, mousePos])

  return (
    <div className="admin-model-management">
      {/* Header */}
      <div className="admin-page-header">
        <h1 className="admin-page-title">工作流编辑器</h1>
        <p className="admin-page-desc">
          可视化编排工作流：从左侧拖入节点，点击节点后再点击另一节点即可连线，右侧编辑节点属性。
        </p>
      </div>

      {/* Toolbar */}
      <div className="admin-toolbar">
        <div className="admin-toolbar-left" style={{ color: 'var(--color-text-secondary)', fontSize: 'var(--text-sm)' }}>
          {connectSource ? (
            <span style={{ color: 'var(--color-primary)', fontWeight: 600 }}>
              连线中：点击目标节点完成连接，再次点击源节点取消
            </span>
          ) : (
            <span>节点 {nodes.length} · 连线 {edges.length}</span>
          )}
        </div>
        <div className="admin-toolbar-right" style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button className="btn btn-secondary" onClick={saveLocal}>
            <ICONS.download size={14} /> 保存
          </button>
          <button className="btn btn-secondary" onClick={loadLocal}>
            <ICONS.refresh size={14} /> 加载
          </button>
          <button className="btn btn-secondary" onClick={clearAll}>
            <ICONS.close size={14} /> 清空
          </button>
          <button className="btn btn-primary" onClick={exportJSON}>
            <ICONS.copy size={14} /> 导出 JSON
          </button>
        </div>
      </div>

      {notice && (
        <div
          style={{
            marginBottom: 12,
            padding: '8px 12px',
            borderRadius: 'var(--radius-sm)',
            background: 'var(--color-primary-subtle)',
            color: 'var(--color-primary)',
            fontSize: 'var(--text-sm)',
          }}
        >
          {notice}
        </div>
      )}

      {/* Editor body */}
      <div
        className="admin-card"
        style={{
          padding: 0,
          display: 'grid',
          gridTemplateColumns: '180px 1fr 260px',
          gap: 0,
          overflow: 'hidden',
          height: 640,
        }}
      >
        {/* Palette */}
        <div
          style={{
            borderRight: '1px solid var(--color-border)',
            padding: 12,
            overflowY: 'auto',
            background: 'var(--color-surface-hover)',
          }}
        >
          <div
            style={{
              fontSize: 'var(--text-xs)',
              color: 'var(--color-text-secondary)',
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
              marginBottom: 8,
            }}
          >
            节点面板
          </div>
          {PALETTE.map((p) => (
            <button
              key={p.type}
              onClick={() => addNode(p)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                width: '100%',
                padding: '8px 10px',
                marginBottom: 6,
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--color-border)',
                background: 'var(--color-surface)',
                cursor: 'pointer',
                fontSize: 'var(--text-sm)',
                color: 'var(--color-text)',
                textAlign: 'left',
              }}
            >
              <span style={{ width: 10, height: 10, borderRadius: 3, background: p.color, flexShrink: 0 }} />
              {p.label}
            </button>
          ))}
          <div
            style={{
              marginTop: 12,
              fontSize: 'var(--text-xs)',
              color: 'var(--color-text-muted)',
              lineHeight: 1.6,
            }}
          >
            点击面板项添加节点；拖拽节点移动；点击节点选中并设为连线起点；Delete 删除选中；点击连线删除。
          </div>
        </div>

        {/* Canvas */}
        <div
          ref={innerRef}
          onMouseDown={onCanvasMouseDown}
          style={{
            position: 'relative',
            overflow: 'auto',
            backgroundImage:
              'linear-gradient(var(--color-border-light) 1px, transparent 1px), linear-gradient(90deg, var(--color-border-light) 1px, transparent 1px)',
            backgroundSize: '24px 24px',
            backgroundColor: 'var(--color-surface)',
          }}
        >
          <div style={{ position: 'relative', width: CANVAS_W, height: CANVAS_H }}>
            {/* SVG edges layer */}
            <svg
              width={CANVAS_W}
              height={CANVAS_H}
              style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}
            >
              <defs>
                <marker
                  id="wf-arrow"
                  viewBox="0 0 10 10"
                  refX="9"
                  refY="5"
                  markerWidth="7"
                  markerHeight="7"
                  orient="auto-start-reverse"
                >
                  <path d="M0,0 L10,5 L0,10 z" fill="var(--color-text-muted)" />
                </marker>
              </defs>
              {edgePaths.map((ep) => (
                <path
                  key={ep.id}
                  d={ep.d}
                  fill="none"
                  stroke="var(--color-text-muted)"
                  strokeWidth={2}
                  markerEnd="url(#wf-arrow)"
                  style={{ pointerEvents: 'stroke', cursor: 'pointer' }}
                  onClick={() => deleteEdge(ep.id)}
                >
                  <title>点击删除该连线</title>
                </path>
              ))}
              {previewPath && (
                <path
                  d={previewPath}
                  fill="none"
                  stroke="var(--color-primary)"
                  strokeWidth={2}
                  strokeDasharray="6 4"
                  opacity={0.7}
                />
              )}
            </svg>

            {/* Nodes */}
            {nodes.length === 0 && edges.length === 0 && (
              <div style={{ position: 'absolute', top: '40%', left: 0, right: 0, display: 'flex', justifyContent: 'center' }}>
                <EmptyState title="画布为空" description="从左侧节点面板点击添加节点以开始编排。" />
              </div>
            )}
            {nodes.map((n) => {
              const pal = paletteOf(n.type)
              const isSelected = n.id === selectedId
              const isSource = n.id === connectSource
              return (
                <div
                  key={n.id}
                  onMouseDown={(e) => onNodeMouseDown(e, n)}
                  style={{
                    position: 'absolute',
                    left: n.x,
                    top: n.y,
                    width: NODE_W,
                    height: NODE_H,
                    borderRadius: 'var(--radius-sm)',
                    border: `1.5px solid ${isSelected ? 'var(--color-primary)' : isSource ? pal.color : 'var(--color-border)'}`,
                    boxShadow: isSelected
                      ? '0 0 0 3px var(--color-primary-subtle)'
                      : isSource
                        ? `0 0 0 3px ${pal.color}33`
                        : 'var(--shadow-sm)',
                    background: 'var(--color-surface)',
                    cursor: 'grab',
                    overflow: 'hidden',
                    display: 'flex',
                    flexDirection: 'column',
                    userSelect: 'none',
                  }}
                >
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                      padding: '4px 8px',
                      borderBottom: '1px solid var(--color-border-light)',
                      background: 'var(--color-surface-hover)',
                      fontSize: 'var(--text-xs)',
                      color: 'var(--color-text-secondary)',
                      flexShrink: 0,
                    }}
                  >
                    <span style={{ width: 8, height: 8, borderRadius: 2, background: pal.color }} />
                    {pal.label}
                  </div>
                  <div
                    style={{
                      padding: '4px 8px',
                      fontSize: 'var(--text-sm)',
                      fontWeight: 600,
                      color: 'var(--color-text)',
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      flex: 1,
                      display: 'flex',
                      alignItems: 'center',
                    }}
                  >
                    {n.name}
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Properties */}
        <div
          style={{
            borderLeft: '1px solid var(--color-border)',
            padding: 12,
            overflowY: 'auto',
            background: 'var(--color-surface)',
          }}
        >
          <div
            style={{
              fontSize: 'var(--text-xs)',
              color: 'var(--color-text-secondary)',
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
              marginBottom: 12,
            }}
          >
            节点属性
          </div>
          {selectedNode ? (
            <div className="admin-form">
              <div className="admin-form-row">
                <label className="admin-form-label">节点类型</label>
                <input
                  className="admin-form-input"
                  value={paletteOf(selectedNode.type).label}
                  disabled
                  style={{ opacity: 0.7 }}
                />
              </div>
              <div className="admin-form-row">
                <label className="admin-form-label">名称</label>
                <input
                  className="admin-form-input"
                  value={selectedNode.name}
                  onChange={(e) => updateNode(selectedNode.id, { name: e.target.value })}
                />
              </div>
              <div className="admin-form-row">
                <label className="admin-form-label">描述</label>
                <input
                  className="admin-form-input"
                  value={selectedNode.description}
                  placeholder="节点用途说明"
                  onChange={(e) => updateNode(selectedNode.id, { description: e.target.value })}
                />
              </div>
              <div className="admin-form-row">
                <label className="admin-form-label">参数 (JSON)</label>
                <textarea
                  className="admin-form-input"
                  value={selectedNode.params}
                  rows={6}
                  placeholder='{}'
                  onChange={(e) => updateNode(selectedNode.id, { params: e.target.value })}
                  style={{ fontFamily: 'var(--font-mono)', minHeight: 120, resize: 'vertical' }}
                />
              </div>
              <button
                className="btn btn-danger"
                style={{ width: '100%', marginTop: 8 }}
                onClick={() => deleteNode(selectedNode.id)}
              >
                <ICONS.close size={14} /> 删除节点
              </button>
            </div>
          ) : (
            <EmptyState title="未选中节点" description="点击画布中的节点以编辑属性。" size="sm" />
          )}
        </div>
      </div>
    </div>
  )
}
