import {
  useState,
  type FormEvent,
  useRef,
  useEffect,
  useCallback,
  memo,
  type ChangeEvent,
  type KeyboardEvent,
} from 'react'
import { useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import i18n from '../i18n/config.ts'
import zhCnResource from '../i18n/locales/zh-CN/agent-chat.json'
import enResource from '../i18n/locales/en/agent-chat.json'
import { generateId } from '../utils/id'
import { getConversation, type ConversationMessage } from '../api/conversations'
import { ICONS } from '../components/ui/Icons'
import ReasoningChain from '../components/ReasoningChain'
import MarkdownRenderer from '../components/MarkdownRenderer'
import { FetchError, getErrorLevel, getErrorLevelLabel, getErrorMessage, type ErrorLevel } from '../utils/errors'
import { parseSlashCommand, renderHelpForRole, type SlashCommand } from '../utils/slashCommands'
import { useAuthStore } from '../stores/authStore'
import SlashCommandPalette from '../components/SlashCommandPalette'
import { toast } from '../components/ui/Toaster'
import { useDevice } from '../context/DeviceContext'
import AgentChatMobile from './mobile/AgentChatMobile'

// 命名空间未在 i18n/config.ts 中注册（按要求不修改该文件），这里在模块加载时
// 同步注入资源，子组件通过 useTranslation('agentChat') 消费。
const NS = 'agentChat'
if (!i18n.hasResourceBundle('zh-CN', NS)) {
  i18n.addResourceBundle('zh-CN', NS, zhCnResource)
}
if (!i18n.hasResourceBundle('en', NS)) {
  i18n.addResourceBundle('en', NS, enResource)
}

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface Message {
  id: string
  role: 'user' | 'agent'
  content: string
  createdAt: Date
  /** Thinking content for this message (if any) */
  thinking?: string
  /** Time spent thinking in ms */
  thinkingTimeMs?: number
  /** Whether thinking panel is expanded */
  thinkingExpanded?: boolean
  /** ReAct reasoning steps from agent */
  reactSteps?: Array<Record<string, unknown>>
  /** Agent confidence score (0-1) */
  confidence?: number
  /** Whether reasoning chain panel is expanded */
  reasoningExpanded?: boolean
  /** Whether generation was stopped/interrupted by user */
  stopped?: boolean
}

interface UploadedFile {
  name: string
  size: number
  type: string
  base64?: string
}

interface SseEvent {
  type: 'start' | 'thinking_token' | 'answer_token' | 'done' | 'error'
  content?: string
  question?: string
  conversation_id?: string
  thinking_time_ms?: number
  message?: string
  payload?: unknown
}

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const SUGGESTION_KEYS = [
  'revenue',
  'netMargin',
  'assetTurnover',
  'liquidity',
  'receivables',
  'pendingReports',
] as const

interface ModelOption {
  id: string
  label: string
  tier: string
}

const REFINE_ACTION_IDS = ['regenerate', 'add_details', 'more_concise', 'polish'] as const

const formatTime = (date: Date) =>
  date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })

const formatSize = (bytes: number) => {
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)}KB`
  return `${(bytes / 1048576).toFixed(1)}MB`
}

/** 读取文件内容为 base64 字符串（不含 data: 前缀）。错误文案由调用方传入（i18n）。 */
const readFileAsBase64 = (
  file: File,
  errors: { nonString: string; readFailed: string },
): Promise<string> =>
  new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = reader.result
      if (typeof result !== 'string') {
        reject(new Error(errors.nonString))
        return
      }
      // result 形如 "data:application/pdf;base64,XXXX" — 去掉前缀
      const commaIdx = result.indexOf(',')
      resolve(commaIdx >= 0 ? result.slice(commaIdx + 1) : result)
    }
    reader.onerror = () => reject(reader.error || new Error(errors.readFailed))
    reader.readAsDataURL(file)
  })

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

/**
 * 单条消息行 —— 用 memo 包裹，避免流式 token 增量更新时其他消息无谓重渲染。
 * 仅当 message 引用变化时才重渲染（流式消息每次 setMessages 会产生新引用，
 * 其他消息保持原引用，自动跳过渲染）。
 */
interface ChatMessageRowProps {
  message: Message
  isStreaming: boolean
  isStreamingTarget: boolean
  hovered: boolean
  onHoverEnter: (id: string) => void
  onHoverLeave: () => void
  onToggleThinking: (id: string) => void
  onToggleReasoning: (id: string) => void
  onCopy: (content: string) => void
  onRefine: (action: string, content: string, messageId: string) => void
  onDelete: (id: string) => void
}

const ChatMessageRow = memo(function ChatMessageRow({
  message,
  isStreaming,
  isStreamingTarget,
  hovered,
  onHoverEnter,
  onHoverLeave,
  onToggleThinking,
  onToggleReasoning,
  onCopy,
  onRefine,
  onDelete,
}: ChatMessageRowProps) {
  const { t } = useTranslation('agentChat')

  const formatThinkingTimeMs = (ms: number) => {
    if (ms < 1000) return `${ms}${t('time.ms')}`
    return `${(ms / 1000).toFixed(1)}${t('time.s')}`
  }

  return (
    <div
      className={`chat-message ${message.role}`}
      onMouseEnter={() => message.role === 'agent' && onHoverEnter(message.id)}
      onMouseLeave={onHoverLeave}
    >
      <div className="chat-avatar" aria-hidden="true">
        {message.role === 'user' ? (
          t('message.me')
        ) : (
          <span className="chat-avatar-glyph">F</span>
        )}
      </div>

      <div className="chat-content">
        {/* ---- Thinking panel (agent messages only) ---- */}
        {message.role === 'agent' && (message.thinking || message.thinkingTimeMs) && (
          <div className="thinking-panel">
            <button
              type="button"
              className="thinking-toggle"
              onClick={() => onToggleThinking(message.id)}
            >
              <span
                className={`thinking-chevron ${message.thinkingExpanded ? 'open' : ''}`}
                aria-hidden="true"
              />
              {message.thinkingExpanded || isStreaming ? (
                <span>
                  {isStreamingTarget
                    ? t('message.thinking')
                    : t('message.thoughtDone', { time: formatThinkingTimeMs(message.thinkingTimeMs || 0) })}
                </span>
              ) : (
                <span>
                  {t('message.thoughtDone', { time: formatThinkingTimeMs(message.thinkingTimeMs || 0) })}
                </span>
              )}
            </button>
            {(message.thinkingExpanded || isStreamingTarget) && message.thinking && (
              <MarkdownRenderer content={message.thinking} className="thinking-content" />
            )}
          </div>
        )}

        {/* ---- Chat bubble ---- */}
        <MarkdownRenderer content={message.content} className="chat-bubble" />
        {isStreamingTarget && <span className="cursor-blink" />}
        {message.stopped && (
          <div className="chat-stopped-mark" role="status">{t('message.stopped')}</div>
        )}

        {/* ---- Confidence badge ---- */}
        {message.role === 'agent' && message.confidence != null && (
          <div className="chat-confidence">
            <span className={`badge ${message.confidence >= 0.7 ? 'success' : message.confidence >= 0.4 ? 'processing' : 'failed'}`}>
              {t('message.confidence', { percent: Math.round(message.confidence * 100) })}
            </span>
          </div>
        )}

        {/* ---- Reasoning chain (collapsible) ---- */}
        {message.role === 'agent' && message.reactSteps && message.reactSteps.length > 0 && (
          <div className="chat-reasoning">
            <button
              type="button"
              className="reasoning-toggle"
              onClick={() => onToggleReasoning(message.id)}
            >
              <ICONS.search size={14} />
              <span>{t('message.reasoningChain', { count: message.reactSteps.length })}</span>
              <span className="reasoning-arrow">{message.reasoningExpanded ? '▼' : '▶'}</span>
            </button>
            {message.reasoningExpanded && (
              <ReasoningChain
                steps={message.reactSteps as Array<Record<string, unknown>> as unknown as Parameters<typeof ReasoningChain>[0]['steps']}
                confidence={message.confidence}
              />
            )}
          </div>
        )}

        {/* ---- Timestamp ---- */}
        <div className="chat-time">{formatTime(message.createdAt)}</div>

        {/* ---- Refinement menu (agent messages, on hover) ---- */}
        {message.role === 'agent' &&
          hovered &&
          message.content &&
          !isStreaming && (
            <div className="chat-refine-menu">
              <button
                type="button"
                className="refine-btn"
                title={t('message.copy')}
                onClick={() => onCopy(message.content)}
              >
                <ICONS.copy size={14} />
                <span>{t('message.copy')}</span>
              </button>
              {REFINE_ACTION_IDS.map((id) => (
                <button
                  key={id}
                  type="button"
                  className="refine-btn"
                  title={t(`refine.${id}`)}
                  onClick={() => onRefine(id, message.content, message.id)}
                >
                  <span>{t(`refine.${id}`)}</span>
                </button>
              ))}
              <button
                type="button"
                className="refine-btn refine-btn-danger"
                title={t('message.delete')}
                onClick={() => onDelete(message.id)}
              >
                <ICONS.close size={14} />
                <span>{t('message.delete')}</span>
              </button>
            </div>
          )}
      </div>
    </div>
  )
})

export default function AgentChatPage() {
  const { t } = useTranslation('agentChat')
  const location = useLocation()
  const params = new URLSearchParams(location.search)
  const initialQuestion = params.get('question') || ''
  const cidFromUrl = params.get('cid') || ''

  // 移动端走独立的全屏对话组件（与桌面侧栏对话完全分离，桌面逻辑零改动）
  const { isMobile } = useDevice()
  if (isMobile) return <AgentChatMobile />

  const [messages, setMessages] = useState<Message[]>([])
  const [conversationId, setConversationId] = useState<string | null>(cidFromUrl || null)
  const [question, setQuestion] = useState(initialQuestion)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [errorLevel, setErrorLevel] = useState<ErrorLevel>('unknown')

  /* --- function bar state --- */
  const [deepThink, setDeepThink] = useState(false)
  const [useWeb, setUseWeb] = useState(false)
  const [availableModels, setAvailableModels] = useState<ModelOption[]>([])
  const [activeModel, setActiveModel] = useState<ModelOption>(() => ({ id: '', label: t('status.loading'), tier: '' }))
  const [showModelDropdown, setShowModelDropdown] = useState(false)
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([])

  /* --- streaming state --- */
  const [streamingMessageId, setStreamingMessageId] = useState<string | null>(null)

  /* --- hover state for refinement menu --- */
  const [hoveredMessageId, setHoveredMessageId] = useState<string | null>(null)

  /* --- slash command palette state --- */
  const [showSlashPalette, setShowSlashPalette] = useState(false)
  const role = useAuthStore((s) => s.role)

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const abortControllerRef = useRef<AbortController | null>(null)
  const initialSubmittedRef = useRef(false)
  const modelDropdownRef = useRef<HTMLDivElement>(null)
  /** 最新 messages 快照，供回调内读取，避免把 messages 放进依赖导致流式期间回调重建 */
  const messagesRef = useRef<Message[]>([])
  /** 最近一次提交的 user 问题，供错误重试使用 */
  const lastQuestionRef = useRef<string>('')
  /** 消息滚动容器，用于判断用户是否停留在底部以决定是否自动跟随 */
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  /** 用户是否处于消息列表底部（true 时流式新 token 才自动滚动跟随） */
  const isAtBottomRef = useRef(true)

  /* ------------------------------------------------------------------ */
  /*  Effects                                                            */
  /* ------------------------------------------------------------------ */

  // 同步 messages 快照，供回调内读取（避免把 messages 放进 useCallback 依赖）
  useEffect(() => {
    messagesRef.current = messages
  }, [messages])

  // 仅在用户停留在底部时自动跟随滚动，避免用户上滚回看历史时被强制拉回
  useEffect(() => {
    if (isAtBottomRef.current) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages, loading, streamingMessageId])

  // 监听消息容器滚动，更新"是否在底部"标记
  useEffect(() => {
    const el = scrollContainerRef.current
    if (!el) return
    const handler = () => {
      const threshold = 80 // 距底部 80px 内视为"在底部"
      isAtBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < threshold
    }
    el.addEventListener('scroll', handler, { passive: true })
    return () => el.removeEventListener('scroll', handler)
  }, [])

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  // question 变化时自适应 textarea 高度（覆盖发送/新建对话等程序化清空场景）
  useEffect(() => {
    const el = inputRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`
  }, [question])

  /* Fetch available models from backend */
  useEffect(() => {
    let cancelled = false
    const baseUrl = import.meta.env.VITE_API_BASE_URL || '/api/v1'
    fetch(`${baseUrl}/agent/models`, { credentials: 'include' })
      .then((r) => r.json())
      .then((data) => {
        if (cancelled) return
        const models: ModelOption[] = data?.data || []
        setAvailableModels(models)
        if (models.length > 0) {
          setActiveModel(models[0])
        }
      })
      .catch(() => {
        if (cancelled) return
        // 降级到硬编码兜底
        const fallback = { id: 'DeepSeek-V4-Pro', label: 'DeepSeek-V4-Pro', tier: 'high' }
        setAvailableModels([fallback])
        setActiveModel(fallback)
      })
    return () => {
      cancelled = true
    }
  }, [])

  /* 从 URL ?cid= 加载历史对话并渲染到消息列表（支持从会话管理页续聊） */
  useEffect(() => {
    if (!cidFromUrl) return
    let cancelled = false
    setLoading(true)
    getConversation(cidFromUrl)
      .then((res) => {
        if (cancelled) return
        const detail = res?.data?.data
        if (!detail || !Array.isArray(detail.messages)) {
          setError(t('errors.conversationNotFound'))
          setErrorLevel('client')
          return
        }
        const loaded: Message[] = detail.messages.map((msg: ConversationMessage) => ({
          id: generateId(),
          role: msg.role === 'assistant' ? 'agent' : (msg.role as 'user' | 'agent'),
          content: msg.content || '',
          createdAt: new Date(msg.timestamp || Date.now()),
          thinkingExpanded: false,
        }))
        setMessages(loaded)
        setConversationId(cidFromUrl)
      })
      .catch((err) => {
        if (cancelled) return
        setError(getErrorMessage(err, t('errors.loadConversationFailed')))
        setErrorLevel(getErrorLevel(err))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cidFromUrl])

  /* Close model dropdown on outside click */
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (
        modelDropdownRef.current &&
        !modelDropdownRef.current.contains(e.target as Node)
      ) {
        setShowModelDropdown(false)
      }
    }
    if (showModelDropdown) {
      document.addEventListener('mousedown', handler)
    }
    return () => document.removeEventListener('mousedown', handler)
  }, [showModelDropdown])

  /* ------------------------------------------------------------------ */
  /*  Streaming submit                                                   */
  /* ------------------------------------------------------------------ */

  const handleSubmitInternal = useCallback(
    async (text: string, refinement?: string) => {
      const trimmed = text.trim()
      if (!trimmed || loading) return

      // Abort any ongoing stream
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }

      const userMessageId = generateId()
      const userMessage: Message = {
        id: userMessageId,
        role: 'user',
        content: trimmed,
        createdAt: new Date(),
      }

      setMessages((prev) => [...prev, userMessage])
      setQuestion('')
      lastQuestionRef.current = trimmed
      setLoading(true)
      setError('')
      setErrorLevel('unknown')
      setStreamingMessageId(null)

      const history = messagesRef.current
        .slice(-10)
        .map((m) => ({
          role: m.role === 'agent' ? 'assistant' : m.role,
          content: m.content,
        }))

      const answerMessageId = `${generateId()}-answer`
      const answerMessage: Message = {
        id: answerMessageId,
        role: 'agent',
        content: '',
        thinking: '',
        createdAt: new Date(),
        thinkingExpanded: true,
      }

      setMessages((prev) => [...prev, answerMessage])
      setStreamingMessageId(answerMessageId)

      const controller = new AbortController()
      abortControllerRef.current = controller

      try {
        const baseUrl = import.meta.env.VITE_API_BASE_URL || '/api/v1'
        const response = await fetch(`${baseUrl}/agent/chat/stream`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({
            question: refinement ? `${refinement}: ${trimmed}` : trimmed,
            conversation_id: conversationId,
            history,
            deep_think: deepThink,
            use_web: useWeb,
            files: uploadedFiles.map((f) => ({
              name: f.name,
              type: f.type,
              size: f.size,
              base64: f.base64,
            })),
            model: activeModel.id,
          }),
          signal: controller.signal,
        })

        if (!response.ok) {
          const text = await response.text()
          throw new FetchError({
            status: response.status,
            url: response.url || `${baseUrl}/agent/chat/stream`,
            method: 'POST',
            bodyText: text,
            message: text || `HTTP ${response.status}`,
          })
        }

        const reader = response.body?.getReader()
        if (!reader) {
          throw new FetchError({
            url: `${baseUrl}/agent/chat/stream`,
            method: 'POST',
            message: t('errors.streamBodyNotReadable'),
          })
        }

        const decoder = new TextDecoder()
        let buffer = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''

          for (const line of lines) {
            const trimmedLine = line.trim()
            if (!trimmedLine.startsWith('data: ')) continue
            const jsonStr = trimmedLine.slice(6)
            if (jsonStr === '[DONE]') continue

            try {
              const event: SseEvent = JSON.parse(jsonStr)
              setMessages((prev) =>
                prev.map((m) => {
                  if (m.id !== answerMessageId) return m

                  switch (event.type) {
                    case 'start':
                      // 提取后端分配的 conversation_id 并同步到 URL，
                      // 使刷新/分享链接可恢复当前会话（此前为 no-op 导致会话丢失）
                      if (event.conversation_id) {
                        setConversationId(event.conversation_id)
                        const url = new URL(window.location.href)
                        url.searchParams.set('cid', event.conversation_id)
                        window.history.replaceState({}, '', url.toString())
                      }
                      return m

                    case 'thinking_token':
                      return { ...m, thinking: (m.thinking || '') + (event.content || '') }

                    case 'answer_token':
                      return { ...m, content: m.content + (event.content || '') }

                    case 'done':
                      return {
                        ...m,
                        thinkingTimeMs: event.thinking_time_ms,
                        thinkingExpanded: false,
                      }

                    case 'error':
                      setError(event.message || t('errors.unknown'))
                      // 后端主动通过 SSE 上报的错误通常属于服务端错误
                      setErrorLevel('server')
                      return m

                    default:
                      return m
                  }
                }),
              )

              if (event.type === 'done') {
                setStreamingMessageId(null)
                // Parse reasoning chain and confidence from done payload
                if (event.payload && typeof event.payload === 'object') {
                  const payload = event.payload as Record<string, unknown>
                  const reactSteps = payload.react_steps as Array<Record<string, unknown>> | undefined
                  const confidence = typeof payload.confidence === 'number' ? payload.confidence : undefined
                  if (reactSteps || confidence != null) {
                    const targetId = answerMessageId
                    setMessages((prev) =>
                      prev.map((m) => {
                        if (m.id === targetId) {
                          return {
                            ...m,
                            reactSteps: reactSteps || m.reactSteps,
                            confidence: confidence ?? m.confidence,
                          }
                        }
                        return m
                      }),
                    )
                  }
                }
              }

              if (event.type === 'error') {
                setStreamingMessageId(null)
              }
            } catch {
              // skip malformed JSON lines
            }
          }
        }
      } catch (err: unknown) {
        if (err instanceof DOMException && err.name === 'AbortError') {
          // user aborted — keep partial content，标记该消息为已中断
          setMessages((prev) =>
            prev.map((m) => (m.id === answerMessageId ? { ...m, stopped: true } : m)),
          )
        } else {
          const msg = getErrorMessage(err, t('errors.connectionInterrupted'))
          if (msg) {
            setError(msg)
            setErrorLevel(getErrorLevel(err))
          }
        }
        setStreamingMessageId(null)
      } finally {
        setLoading(false)
      }
    },
    [loading, conversationId, deepThink, useWeb, activeModel, uploadedFiles, t],
  )

  /* ------------------------------------------------------------------ */
  /*  Auto-submit initial question                                       */
  /* ------------------------------------------------------------------ */

  useEffect(() => {
    if (initialQuestion && !initialSubmittedRef.current) {
      initialSubmittedRef.current = true
      void handleSubmitInternal(initialQuestion)
    }
  }, [initialQuestion, handleSubmitInternal])

  /* ------------------------------------------------------------------ */
  /*  Handlers                                                           */
  /* ------------------------------------------------------------------ */

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    // 斜杠命令优先处理 —— 不走 LLM 对话流
    if (question.trim().startsWith('/')) {
      void executeSlashCommand(question)
      return
    }
    void handleSubmitInternal(question)
  }

  /* ------------------------------------------------------------------ */
  /*  Slash command execution                                            */
  /* ------------------------------------------------------------------ */

  const executeSlashCommand = useCallback(
    async (raw: string) => {
      const userMessageId = generateId()
      const userMessage: Message = {
        id: userMessageId,
        role: 'user',
        content: raw.trim(),
        createdAt: new Date(),
      }
      setMessages((prev) => [...prev, userMessage])
      setQuestion('')
      setShowSlashPalette(false)
      setError('')
      setErrorLevel('unknown')
      setLoading(true)

      const answerId = `${generateId()}-answer`
      const answerMessage: Message = {
        id: answerId,
        role: 'agent',
        content: '',
        createdAt: new Date(),
      }
      setMessages((prev) => [...prev, answerMessage])
      setStreamingMessageId(answerId)

      try {
        // help 命令特殊处理（避免循环依赖）
        if (raw.trim() === '/help' || raw.trim() === '/?') {
          const helpMarkdown = renderHelpForRole(role)
          setMessages((prev) =>
            prev.map((m) => (m.id === answerId ? { ...m, content: helpMarkdown } : m)),
          )
          return
        }

        const parsed = parseSlashCommand(raw, role)
        if (!parsed) {
          // 不是斜杠命令（理论不会走到这里，因为外层已过滤）
          throw new Error(t('errors.unparsableCommand'))
        }
        const result = await parsed.command.handler(parsed.args)
        setMessages((prev) =>
          prev.map((m) => (m.id === answerId ? { ...m, content: result } : m)),
        )
      } catch (err) {
        const msg = err instanceof Error ? err.message : t('errors.commandExecutionFailed')
        setError(msg)
        setErrorLevel(getErrorLevel(err) === 'unknown' ? 'client' : getErrorLevel(err))
        // 把空 answer 消息删掉，避免出现一个空气泡
        setMessages((prev) => prev.filter((m) => m.id !== answerId))
      } finally {
        setLoading(false)
        setStreamingMessageId(null)
      }
    },
    [role, t],
  )

  /** 从面板选中命令时，填充到输入框（让用户继续输入参数） */
  const handleSlashPaletteSelect = (cmd: SlashCommand) => {
    // 如果命令没有参数，直接执行
    if (cmd.args.length === 0) {
      void executeSlashCommand(`/${cmd.name}`)
      return
    }
    // 否则填入命令名 + 一个空格，让用户继续输入参数
    setQuestion(`/${cmd.name} `)
    setShowSlashPalette(false)
    // 焦点回到输入框
    setTimeout(() => inputRef.current?.focus(), 0)
  }

  /** 输入框键盘事件：面板可见时让面板接管方向键；Enter 发送 / Shift+Enter 换行 */
  const handleInputKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (showSlashPalette) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'Escape') {
        e.preventDefault()
        // SlashCommandPalette 的全局 keydown 监听会处理这些键
        return
      }
      if (e.key === 'Enter') {
        // 面板接管 Enter，由 palette 触发选择
        e.preventDefault()
        return
      }
    }
    // Enter 发送 / Shift+Enter 换行（IME 组字中不触发，避免中文输入被打断）
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      const q = question.trim()
      if (!q || loading) return
      if (q.startsWith('/')) {
        void executeSlashCommand(question)
      } else {
        void handleSubmitInternal(question)
      }
    }
  }

  /** 自适应高度：根据 scrollHeight 调整 textarea 高度，上限 200px（约 8 行） */
  const autoResizeInput = () => {
    const el = inputRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`
  }

  /** 输入框内容变化时，决定是否显示 slash 面板 */
  const handleInputChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value
    setQuestion(value)
    autoResizeInput()
    // 仅当输入以 / 开头且尚未按空格定参时显示面板
    const trimmed = value.trim()
    if (trimmed.startsWith('/') && !trimmed.includes(' ')) {
      setShowSlashPalette(true)
    } else {
      setShowSlashPalette(false)
    }
  }

  const onSuggestionClick = (text: string) => {
    void handleSubmitInternal(text)
  }

  const handleFileChange = async (e: ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (!files) return
    const newFiles: UploadedFile[] = []
    for (let i = 0; i < files.length; i++) {
      const f = files[i]
      if (f.size > 50 * 1024 * 1024) {
        setError(t('errors.fileTooLarge', { name: f.name }))
        continue
      }
      // 读取文件内容为 base64，让后端真正解析与注入 agent 上下文
      try {
        const base64 = await readFileAsBase64(f, {
          nonString: t('errors.fileReaderNonString'),
          readFailed: t('errors.fileReadFailed'),
        })
        newFiles.push({ name: f.name, size: f.size, type: f.type, base64 })
      } catch (err) {
        setError(t('errors.fileReadFailedWrapper', { name: f.name, message: (err as Error).message }))
      }
    }
    setUploadedFiles((prev) => [...prev, ...newFiles].slice(0, 5))
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const removeFile = (name: string) => {
    setUploadedFiles((prev) => prev.filter((f) => f.name !== name))
  }

  const toggleThinking = (msgId: string) => {
    setMessages((prev) =>
      prev.map((m) =>
        m.id === msgId ? { ...m, thinkingExpanded: !m.thinkingExpanded } : m,
      ),
    )
  }

  const handleCopy = async (content: string) => {
    try {
      await navigator.clipboard.writeText(content)
      toast.success(t('toast.copySuccess'))
    } catch {
      toast.error(t('toast.copyFailed'))
    }
  }

  const handleRefine = (action: string, msgContent: string, messageId: string) => {
    if (action === 'regenerate') {
      // 重新生成：基于该 agent 回答对应的上一条 user 提问重新生成，
      // 而非把 agent 回答当问题重发（此前逻辑反了，导致越生成越偏）
      const list = messagesRef.current
      const idx = list.findIndex((m) => m.id === messageId)
      if (idx < 0) return
      // 向前找最近一条 user 消息作为原始问题
      let originalQuestion = ''
      for (let i = idx - 1; i >= 0; i--) {
        if (list[i].role === 'user') {
          originalQuestion = list[i].content
          break
        }
      }
      if (!originalQuestion) return
      // 移除当前这条 agent 回答，避免重复，再以原问题重新提交
      setMessages((prev) => prev.filter((m) => m.id !== messageId))
      void handleSubmitInternal(originalQuestion)
      return
    }

    const prompts: Record<string, string> = {
      add_details: t('refinePrompts.add_details'),
      more_concise: t('refinePrompts.more_concise'),
      polish: t('refinePrompts.polish'),
    }
    const refinement = prompts[action] || ''
    if (refinement) {
      void handleSubmitInternal(`${refinement}：\n\n${msgContent}`)
    }
  }

  const handleDeleteMessage = (msgId: string) => {
    setMessages((prev) => prev.filter((m) => m.id !== msgId))
  }

  const handleStop = () => {
    // 手动中断当前流式请求（此前仅在新提交时自动 abort，用户无法主动停止）
    const targetId = streamingMessageId
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }
    // 标记当前流式消息为已中断，让用户立刻看到"已停止生成"
    if (targetId) {
      setMessages((prev) =>
        prev.map((m) => (m.id === targetId ? { ...m, stopped: true } : m)),
      )
    }
    setLoading(false)
    setStreamingMessageId(null)
  }

  /** 错误后重试：用最近一次提交的 user 问题重新发起 */
  const handleRetry = () => {
    const q = lastQuestionRef.current
    if (!q) return
    setError('')
    setErrorLevel('unknown')
    void handleSubmitInternal(q)
  }

  const handleNewChat = () => {
    // 新建对话：中断当前流、清空消息与 conversationId、清除 URL cid 参数
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }
    setMessages([])
    setConversationId(null)
    setLoading(false)
    setStreamingMessageId(null)
    setError('')
    setQuestion('')
    const url = new URL(window.location.href)
    url.searchParams.delete('cid')
    url.searchParams.delete('question')
    window.history.replaceState({}, '', url.toString())
    inputRef.current?.focus()
  }

  /* ------------------------------------------------------------------ */
  /*  Render                                                             */
  /* ------------------------------------------------------------------ */

  const hasContent = messages.length > 0
  const isStreaming = streamingMessageId !== null

  return (
    <div className="container">
      <div className="page-header">
        <div>
          <h1>{t('title')}</h1>
          <p className="text-muted text-sm">{t('subtitle')}</p>
        </div>
        <button
          type="button"
          className="btn btn-outline"
          onClick={handleNewChat}
          title={t('newChat')}
        >
          + {t('newChat')}
        </button>
      </div>

      <div className="card chat-container">
        <div className="chat-messages" ref={scrollContainerRef}>
          {!hasContent ? (
            /* ----- Empty state ----- */
            <div className="chat-empty">
              <div className="chat-empty-glyph" aria-hidden="true">
                FA
              </div>
              <h4 className="chat-empty-title">{t('empty.title')}</h4>
              <p className="chat-empty-desc">
                {t('empty.desc')}
              </p>
              <div className="chat-quick-prompts">
                {SUGGESTION_KEYS.map((key) => (
                  <button
                    key={key}
                    type="button"
                    className="chip"
                    onClick={() => onSuggestionClick(t(`suggestions.${key}`))}
                    disabled={loading}
                  >
                    {t(`suggestions.${key}`)}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            /* ----- Messages ----- */
            messages.map((message) => (
              <ChatMessageRow
                key={message.id}
                message={message}
                isStreaming={isStreaming}
                isStreamingTarget={isStreaming && message.id === streamingMessageId}
                hovered={hoveredMessageId === message.id}
                onHoverEnter={setHoveredMessageId}
                onHoverLeave={() => setHoveredMessageId(null)}
                onToggleThinking={toggleThinking}
                onToggleReasoning={(id) =>
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === id ? { ...m, reasoningExpanded: !m.reasoningExpanded } : m,
                    ),
                  )
                }
                onCopy={handleCopy}
                onRefine={handleRefine}
                onDelete={handleDeleteMessage}
              />
            ))
          )}

          {/* ----- Typing indicator (fallback, when streaming hasn't started yet) ----- */}
          {loading && !isStreaming && (
            <div className="chat-message agent">
              <div className="chat-avatar" aria-hidden="true">
                <span className="chat-avatar-glyph">F</span>
              </div>
              <div className="chat-content">
                <div className="chat-bubble chat-typing">
                  <span className="chat-typing-dot" />
                  <span className="chat-typing-dot" />
                  <span className="chat-typing-dot" />
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* ----- Error bar（按级别打灯高亮） ----- */}
        {error && (
          <div className={`chat-error-bar level-${errorLevel}`} role="alert">
            <span className="chat-error-icon" aria-hidden="true">!</span>
            <span className="chat-error-level">{getErrorLevelLabel(errorLevel)}</span>
            <span className="chat-error-text">{error}</span>
            {lastQuestionRef.current && (
              <button
                type="button"
                className="chat-error-retry"
                onClick={handleRetry}
                disabled={loading}
              >
                {t('errorBar.retry')}
              </button>
            )}
            <button
              type="button"
              className="chat-error-close"
              onClick={() => {
                setError('')
                setErrorLevel('unknown')
              }}
              aria-label={t('errorBar.closeAria')}
            >
              <ICONS.close size={14} />
            </button>
          </div>
        )}

        {/* ----- Uploaded files preview ----- */}
        {uploadedFiles.length > 0 && (
          <div className="chat-files-bar">
            {uploadedFiles.map((f) => (
              <span key={f.name} className="chat-file-tag">
                <span className="chat-file-tag-name">{f.name}</span>
                <span className="chat-file-tag-size">{formatSize(f.size)}</span>
                <button
                  type="button"
                  className="chat-file-tag-remove"
                  onClick={() => removeFile(f.name)}
                  aria-label={t('files.removeAria', { name: f.name })}
                >
                  <ICONS.close size={12} />
                </button>
              </span>
            ))}
          </div>
        )}

        {/* ----- Function bar ----- */}
        <div className="chat-function-bar">
          <button
            type="button"
            className={`func-btn ${deepThink ? 'active' : ''}`}
            onClick={() => setDeepThink((v) => !v)}
            title={t('functionBar.deepThink')}
            aria-pressed={deepThink}
          >
            <ICONS.reflections size={16} className="func-btn-icon" />
            <span>{t('functionBar.deepThink')}</span>
          </button>

          <button
            type="button"
            className={`func-btn ${useWeb ? 'active' : ''}`}
            onClick={() => setUseWeb((v) => !v)}
            title={t('functionBar.useWeb')}
            aria-pressed={useWeb}
          >
            <ICONS.search size={16} className="func-btn-icon" />
            <span>{t('functionBar.useWeb')}</span>
          </button>

          <button
            type="button"
            className="func-btn"
            onClick={() => fileInputRef.current?.click()}
            title={t('functionBar.uploadFile')}
          >
            <ICONS.documents size={16} className="func-btn-icon" />
            <span>{t('functionBar.uploadFile')}</span>
          </button>
          <input
            ref={fileInputRef}
            type="file"
            className="file-input-hidden"
            accept=".pdf,.xlsx,.xls,.csv,.doc,.docx,.png,.jpg,.jpeg,.txt"
            multiple
            onChange={handleFileChange}
          />

          {/* Model selector */}
          <div className="model-selector" ref={modelDropdownRef}>
            <button
              type="button"
              className="func-btn model-btn"
              onClick={() => setShowModelDropdown((v) => !v)}
              title={t('functionBar.switchModel')}
            >
              <span className="func-btn-model-label">{t('functionBar.model')}</span>
              <span className="func-btn-model-name">{activeModel.label}</span>
              <span className={`func-btn-model-chevron ${showModelDropdown ? 'open' : ''}`}>
                ▾
              </span>
            </button>
            {showModelDropdown && (
              <div className="model-dropdown">
                {availableModels.map((m) => (
                  <button
                    key={m.id}
                    type="button"
                    className={`model-dropdown-item ${activeModel.id === m.id ? 'selected' : ''}`}
                    onClick={() => {
                      setActiveModel(m)
                      setShowModelDropdown(false)
                    }}
                  >
                    <span className="model-dropdown-check">
                      {activeModel.id === m.id ? '✓' : ''}
                    </span>
                    <span>{m.label}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* ----- Input ----- */}
        <form onSubmit={handleSubmit} className="chat-input">
          <div className="chat-input-wrapper">
            {showSlashPalette && (
              <SlashCommandPalette
                role={role}
                query={question}
                onSelect={handleSlashPaletteSelect}
                onClose={() => setShowSlashPalette(false)}
              />
            )}
            <button
              type="button"
              className="chat-slash-trigger"
              onClick={() => {
                if (!question.trim().startsWith('/')) {
                  setQuestion('/')
                  setShowSlashPalette(true)
                  setTimeout(() => inputRef.current?.focus(), 0)
                }
              }}
              title={t('input.slashPaletteTitle')}
              aria-label={t('input.slashPaletteAria')}
              disabled={loading}
            >
              /
            </button>
            <textarea
              ref={inputRef}
              className="chat-input-field"
              value={question}
              onChange={handleInputChange}
              onKeyDown={handleInputKeyDown}
              placeholder={t('input.placeholder')}
              rows={1}
              aria-label={t('input.ariaLabel')}
            />
            {isStreaming ? (
              <button
                type="button"
                className="chat-send chat-stop"
                onClick={handleStop}
                aria-label={t('input.stopTitle')}
                title={t('input.stopTitle')}
              >
                <ICONS.stop size={16} />
                <span>{t('input.stop')}</span>
              </button>
            ) : (
              <button
                type="submit"
                className="chat-send"
                disabled={!question.trim()}
                aria-label={t('input.sendAria')}
              >
                <ICONS.send size={16} />
                <span>{t('input.send')}</span>
              </button>
            )}
          </div>
        </form>
      </div>
    </div>
  )
}
