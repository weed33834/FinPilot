import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * useWebSocket
 * ------------
 * 通用 WebSocket Hook，支持自动连接、指数退避重连、心跳、消息队列与连接状态追踪。
 *
 * 后端协议（见 backend/app/services/websocket_service.py）：
 *  - 连接时通过 query 参数 tenant_id 标识租户
 *  - 客户端发送 "ping"，服务端回复 "pong"（心跳）
 *  - 服务端推送 JSON：{ type, data, timestamp }
 */

export type WebSocketStatus = 'connecting' | 'connected' | 'disconnected' | 'error'

export interface WebSocketMessage {
  type: string
  data: unknown
  timestamp: string
}

export interface UseWebSocketOptions {
  /** 完整 WebSocket URL；未提供则根据当前页面 host 自动推导 */
  url?: string
  /** 租户 ID，作为 tenant_id query 参数传递（鉴权） */
  tenantId?: string
  /** 收到非心跳消息时的回调 */
  onMessage?: (msg: WebSocketMessage) => void
  /** 是否启用自动重连，默认 true */
  reconnect?: boolean
  /** 初始重连间隔（ms），默认 1000 */
  reconnectInterval?: number
  /** 最大重连次数，默认 10 */
  maxReconnectAttempts?: number
  /** 心跳间隔（ms），默认 30000 */
  heartbeatInterval?: number
}

export interface UseWebSocketResult {
  status: WebSocketStatus
  connected: boolean
  /** 发送消息（断线时进入队列，重连后自动 flush）；返回是否已立即发送 */
  send: (data: string | object) => boolean
  /** 主动断开（不再自动重连） */
  disconnect: () => void
  /** 强制重新连接 */
  reconnect: () => void
}

/** 推导默认 WebSocket URL：基于当前页面 host + /ws/notifications */
function buildDefaultUrl(tenantId?: string): string | null {
  if (typeof window === 'undefined') return null
  const envUrl = import.meta.env.VITE_WS_URL as string | undefined
  let base: string
  if (envUrl) {
    base = envUrl
  } else {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    base = `${proto}//${window.location.host}/ws/notifications`
  }
  if (!tenantId) return base
  const sep = base.includes('?') ? '&' : '?'
  return `${base}${sep}tenant_id=${encodeURIComponent(tenantId)}`
}

export function useWebSocket(options: UseWebSocketOptions = {}): UseWebSocketResult {
  const {
    url,
    tenantId,
    reconnect: autoReconnect = true,
    reconnectInterval = 1000,
    maxReconnectAttempts = 10,
    heartbeatInterval = 30000,
  } = options

  const [status, setStatus] = useState<WebSocketStatus>('disconnected')

  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimerRef = useRef<number | null>(null)
  const heartbeatTimerRef = useRef<number | null>(null)
  const attemptRef = useRef(0)
  const manualCloseRef = useRef(false)
  const queueRef = useRef<string[]>([])
  const onMessageRef = useRef(options.onMessage)
  onMessageRef.current = options.onMessage

  const resolvedUrl = url ?? buildDefaultUrl(tenantId)

  const clearTimers = useCallback(() => {
    if (reconnectTimerRef.current !== null) {
      window.clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }
    if (heartbeatTimerRef.current !== null) {
      window.clearInterval(heartbeatTimerRef.current)
      heartbeatTimerRef.current = null
    }
  }, [])

  const connect = useCallback(() => {
    if (typeof window === 'undefined' || typeof WebSocket === 'undefined') return
    if (!resolvedUrl) return

    // 关闭既有连接
    if (wsRef.current) {
      try {
        wsRef.current.onclose = null
        wsRef.current.close()
      } catch {
        /* ignore */
      }
      wsRef.current = null
    }
    clearTimers()
    manualCloseRef.current = false
    setStatus('connecting')

    let ws: WebSocket
    try {
      ws = new WebSocket(resolvedUrl)
    } catch {
      setStatus('error')
      return
    }
    wsRef.current = ws

    ws.onopen = () => {
      attemptRef.current = 0
      setStatus('connected')
      // 启动心跳
      heartbeatTimerRef.current = window.setInterval(() => {
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
          try {
            wsRef.current.send('ping')
          } catch {
            /* ignore */
          }
        }
      }, heartbeatInterval)
      // flush 队列
      if (queueRef.current.length > 0) {
        const pending = queueRef.current.splice(0)
        for (const msg of pending) {
          try {
            ws.send(msg)
          } catch {
            queueRef.current.push(msg)
          }
        }
      }
    }

    ws.onmessage = (event: MessageEvent) => {
      const raw = typeof event.data === 'string' ? event.data : ''
      if (raw === 'pong') return // 心跳响应，忽略
      try {
        const msg = JSON.parse(raw) as WebSocketMessage
        if (msg && typeof msg.type === 'string') {
          onMessageRef.current?.(msg)
        }
      } catch {
        // 非 JSON 文本，忽略
      }
    }

    ws.onerror = () => {
      setStatus('error')
    }

    ws.onclose = () => {
      clearTimers()
      wsRef.current = null
      if (manualCloseRef.current) {
        setStatus('disconnected')
        return
      }
      setStatus('disconnected')
      if (autoReconnect && attemptRef.current < maxReconnectAttempts) {
        // 指数退避：1s, 2s, 4s, 8s ... 上限 30s
        const delay = Math.min(reconnectInterval * 2 ** attemptRef.current, 30000)
        attemptRef.current += 1
        reconnectTimerRef.current = window.setTimeout(() => {
          connect()
        }, delay)
      }
    }
  }, [resolvedUrl, autoReconnect, reconnectInterval, maxReconnectAttempts, heartbeatInterval, clearTimers])

  // 自动连接 & 依赖变化时重连
  useEffect(() => {
    if (!resolvedUrl) return
    connect()
    return () => {
      manualCloseRef.current = true
      clearTimers()
      if (wsRef.current) {
        try {
          wsRef.current.onclose = null
          wsRef.current.close()
        } catch {
          /* ignore */
        }
        wsRef.current = null
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resolvedUrl])

  const send = useCallback((data: string | object): boolean => {
    const payload = typeof data === 'string' ? data : JSON.stringify(data)
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      try {
        wsRef.current.send(payload)
        return true
      } catch {
        queueRef.current.push(payload)
        return false
      }
    }
    queueRef.current.push(payload)
    return false
  }, [])

  const disconnect = useCallback(() => {
    manualCloseRef.current = true
    clearTimers()
    if (wsRef.current) {
      try {
        wsRef.current.onclose = null
        wsRef.current.close()
      } catch {
        /* ignore */
      }
      wsRef.current = null
    }
    setStatus('disconnected')
  }, [clearTimers])

  const reconnect = useCallback(() => {
    manualCloseRef.current = false
    attemptRef.current = 0
    connect()
  }, [connect])

  return {
    status,
    connected: status === 'connected',
    send,
    disconnect,
    reconnect,
  }
}
