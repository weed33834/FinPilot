import { useCallback, useRef, useState } from 'react'
import { generateId } from '../utils/id'

export interface ChatMessage {
  id: string
  role: 'user' | 'agent'
  content: string
  createdAt: Date
  thinking?: string
  thinkingTimeMs?: number
  reactSteps?: Array<Record<string, unknown>>
  confidence?: number
  stopped?: boolean
}

interface SseEvent {
  type: string
  content?: string
  message?: string
  conversation_id?: string
  thinking_time_ms?: number
  payload?: Record<string, unknown>
}

export interface SendOptions {
  deepThink?: boolean
  useWeb?: boolean
  files?: { name: string; type?: string; size?: number; base64?: string }[]
}

/**
 * 移动端对话流式 Hook（与桌面 AgentChatPage 协议一致，但为移动端独立实现）：
 * - POST {baseUrl}/agent/chat/stream，逐帧解析 SSE（data: 前缀，type 字段）
 * - 思考过程与回答分别累积，done 时补充 reactSteps/confidence
 * - 不依赖对话列表/URL 同步等桌面专属逻辑，保持轻量、可单测
 */
export function useAgentChatStream() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [loading, setLoading] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const convIdRef = useRef<string | null>(null)

  const stop = useCallback(() => {
    abortRef.current?.abort()
    setStreaming(false)
    setLoading(false)
    setMessages((prev) =>
      prev.map((m) =>
        m.role === 'agent' && m.content === '' ? { ...m, stopped: true } : m
      )
    )
  }, [])

  const reset = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    convIdRef.current = null
    setMessages([])
    setError(null)
    setLoading(false)
    setStreaming(false)
  }, [])

  const send = useCallback(async (text: string, options: SendOptions = {}) => {
    const content = text.trim()
    if (!content && !(options.files && options.files.length > 0)) return

    const userMsg: ChatMessage = {
      id: generateId(),
      role: 'user',
      content,
      createdAt: new Date(),
    }
    const answerId = generateId()
    const answerMsg: ChatMessage = {
      id: answerId,
      role: 'agent',
      content: '',
      thinking: '',
      createdAt: new Date(),
    }
    setMessages((prev) => [...prev, userMsg, answerMsg])
    setLoading(true)
    setStreaming(true)
    setError(null)

    const controller = new AbortController()
    abortRef.current = controller
    const baseUrl = import.meta.env.VITE_API_BASE_URL || '/api/v1'

    try {
      const res = await fetch(`${baseUrl}/agent/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          question: content,
          conversation_id: convIdRef.current,
          history: [],
          deep_think: options.deepThink ?? false,
          use_web: options.useWeb ?? false,
          files: options.files ?? [],
        }),
        signal: controller.signal,
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const reader = res.body?.getReader()
      if (!reader) throw new Error('stream not readable')

      const decoder = new TextDecoder()
      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          const trimmed = line.trim()
          if (!trimmed.startsWith('data: ')) continue
          const jsonStr = trimmed.slice(6)
          if (jsonStr === '[DONE]') continue
          let ev: SseEvent
          try {
            ev = JSON.parse(jsonStr)
          } catch {
            continue
          }
          if (ev.type === 'error') {
            setError(ev.message || 'error')
            continue
          }
          setMessages((prev) =>
            prev.map((m) => {
              if (m.id !== answerId) return m
              switch (ev.type) {
                case 'start':
                  if (ev.conversation_id) convIdRef.current = ev.conversation_id
                  return m
                case 'thinking_token':
                  return { ...m, thinking: (m.thinking || '') + (ev.content || '') }
                case 'answer_token':
                  return { ...m, content: m.content + (ev.content || '') }
                case 'done':
                  return { ...m, thinkingTimeMs: ev.thinking_time_ms }
                default:
                  return m
              }
            })
          )
          if (ev.type === 'done' && ev.payload && typeof ev.payload === 'object') {
            const p = ev.payload as Record<string, unknown>
            const reactSteps = p.react_steps as
              | Array<Record<string, unknown>>
              | undefined
            const confidence =
              typeof p.confidence === 'number' ? p.confidence : undefined
            if (reactSteps || confidence != null) {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === answerId
                    ? {
                        ...m,
                        reactSteps: reactSteps ?? m.reactSteps,
                        confidence: confidence ?? m.confidence,
                      }
                    : m
                )
              )
            }
          }
        }
      }
    } catch (e) {
      if ((e as Error).name !== 'AbortError') setError((e as Error).message)
    } finally {
      setStreaming(false)
      setLoading(false)
      abortRef.current = null
    }
  }, [])

  return { messages, loading, streaming, error, send, stop, reset }
}

export default useAgentChatStream
