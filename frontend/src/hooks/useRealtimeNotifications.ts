import { useCallback, useMemo, useState } from 'react'
import { useAuthStore } from '../stores/authStore.ts'
import { generateId } from '../utils/id.ts'
import { useWebSocket, type WebSocketMessage, type WebSocketStatus } from './useWebSocket.ts'

/**
 * useRealtimeNotifications
 * ------------------------
 * 基于 useWebSocket 监听后端实时推送，聚合为通知列表。
 *
 * 监听事件类型：
 *  - report_status / report.status_changed：报告生成进度
 *  - hitl_request / hitl.created：HITL 审批请求
 *  - tool_health：工具健康变更
 *  - agent_status：Agent 运行/完成状态
 *  - subscription.completed：订阅报告完成
 *
 * tenant_id 取自当前登录用户 ID（authStore 未暴露 tenant_id，以用户标识兜底）。
 */

export interface RealtimeNotification {
  id: string
  type: string
  title: string
  message: string
  timestamp: string
  read: boolean
  level: 'info' | 'success' | 'warning' | 'error'
}

const TYPE_META: Record<string, { title: string; level: RealtimeNotification['level'] }> = {
  report_status: { title: '报告状态更新', level: 'info' },
  'report.status_changed': { title: '报告状态更新', level: 'info' },
  hitl_request: { title: '待审批请求', level: 'warning' },
  'hitl.created': { title: '待审批请求', level: 'warning' },
  tool_health: { title: '工具健康变更', level: 'warning' },
  'tool.health_changed': { title: '工具健康变更', level: 'warning' },
  agent_status: { title: 'Agent 状态变更', level: 'info' },
  'agent.status_changed': { title: 'Agent 状态变更', level: 'info' },
  'subscription.completed': { title: '订阅报告完成', level: 'success' },
}

function extractMessage(data: unknown): string {
  if (data == null) return ''
  if (typeof data === 'string') return data
  if (typeof data === 'object') {
    const obj = data as Record<string, unknown>
    const candidates = [
      'message',
      'title',
      'report_title',
      'status',
      'reason',
      'detail',
      'description',
    ]
    for (const key of candidates) {
      const v = obj[key]
      if (typeof v === 'string' && v) return v
    }
    try {
      return JSON.stringify(data)
    } catch {
      return ''
    }
  }
  return String(data)
}

function toNotification(msg: WebSocketMessage): RealtimeNotification {
  const meta = TYPE_META[msg.type] || { title: '实时通知', level: 'info' as const }
  return {
    id: generateId(),
    type: msg.type,
    title: meta.title,
    message: extractMessage(msg.data),
    timestamp: msg.timestamp || new Date().toISOString(),
    read: false,
    level: meta.level,
  }
}

export interface UseRealtimeNotificationsResult {
  notifications: RealtimeNotification[]
  unreadCount: number
  markRead: () => void
  clear: () => void
  connected: boolean
  status: WebSocketStatus
}

export function useRealtimeNotifications(): UseRealtimeNotificationsResult {
  const userId = useAuthStore((s) => s.userId)
  const tenantId = userId || 'default'

  const [notifications, setNotifications] = useState<RealtimeNotification[]>([])

  const onMessage = useCallback((msg: WebSocketMessage) => {
    setNotifications((prev) => [toNotification(msg), ...prev].slice(0, 50))
  }, [])

  const { connected, status } = useWebSocket({
    tenantId,
    onMessage,
    reconnect: true,
  })

  const unreadCount = useMemo(
    () => notifications.reduce((acc, n) => (n.read ? acc : acc + 1), 0),
    [notifications],
  )

  const markRead = useCallback(() => {
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })))
  }, [])

  const clear = useCallback(() => setNotifications([]), [])

  return { notifications, unreadCount, markRead, clear, connected, status }
}
