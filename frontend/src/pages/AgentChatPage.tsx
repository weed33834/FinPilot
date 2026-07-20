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
import { generateId } from '../utils/id'
import { ICONS } from '../components/ui/Icons'
import ReasoningChain from '../components/ReasoningChain'
import MarkdownRenderer from '../components/MarkdownRenderer'
import { FetchError, getErrorLevel, getErrorLevelLabel, getErrorMessage, type ErrorLevel } from '../utils/errors'
import { parseSlashCommand, renderHelpForRole, type SlashCommand } from '../utils/slashCommands'
import { useAuthStore } from '../stores/authStore'
import SlashCommandPalette from '../components/SlashCommandPalette'

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
}

interface UploadedFile {
  name: string
  size: number
  type: string
  base64?: string
}

interface SseEvent {
  type: 'start' | 'thinking' | 'thinking_token' | 'answer_token' | 'done' | 'error' | 'interrupt'
  content?: string
  question?: string
  thinking_time_ms?: number
  message?: string
  payload?: unknown
}

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const SUGGESTIONS = [
  '本月营业收入及同比变化',
  '最新季度净利润率',
  '总资产周转率趋势分析',
  '流动比率与速动比率',
  '应收账款账龄分布',
  '最近待审批报告',
]

const AVAILABLE_MODELS = [
  { id: 'qwen3.5:9b', label: 'Qwen3.5 9B' },
  { id: 'qwen3:14b', label: 'Qwen3 14B' },
  { id: 'deepseek-r1:8b', label: 'DeepSeek-R1 8B' },
  { id: 'deepseek-r1:14b', label: 'DeepSeek-R1 14B' },
  { id: 'glm4:9b', label: 'GLM-4 9B' },
]

const REFINE_ACTIONS = [
  { id: 'regenerate', label: '重新生成', icon: 'refresh' },
  { id: 'add_details', label: '添加细节', icon: '' },
  { id: 'more_concise', label: '更简洁', icon: '' },
  { id: 'polish', label: '润色', icon: '' },
] as const

const formatTime = (date: Date) =>
  date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })

const formatSize = (bytes: number) => {
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)}KB`
  return `${(bytes / 1048576).toFixed(1)}MB`
}

/** 读取文件内容为 base64 字符串（不含 data: 前缀）。 */
const readFileAsBase64 = (file: File): Promise<string> =>
  new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = reader.result
      if (typeof result !== 'string') {
        reject(new Error('FileReader 返回非字符串'))
        return
      }
      // result 形如 "data:application/pdf;base64,XXXX" — 去掉前缀
      const commaIdx = result.indexOf(',')
      resolve(commaIdx >= 0 ? result.slice(commaIdx + 1) : result)
    }
    reader.onerror = () => reject(reader.error || new Error('文件读取失败'))
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
  onRefine: (action: string, content: string) => void
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
  const formatThinkingTimeMs = (ms: number) => {
    if (ms < 1000) return `${ms}毫秒`
    return `${(ms / 1000).toFixed(1)}秒`
  }

  return (
    <div
      className={`chat-message ${message.role}`}
      onMouseEnter={() => message.role === 'agent' && onHoverEnter(message.id)}
      onMouseLeave={onHoverLeave}
    >
      <div className="chat-avatar" aria-hidden="true">
        {message.role === 'user' ? (
          '我'
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
                    ? '思考中...'
                    : `已深度思考（${formatThinkingTimeMs(message.thinkingTimeMs || 0)}）`}
                </span>
              ) : (
                <span>
                  已深度思考（{formatThinkingTimeMs(message.thinkingTimeMs || 0)}）
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

        {/* ---- Confidence badge ---- */}
        {message.role === 'agent' && message.confidence != null && (
          <div className="chat-confidence">
            <span className={`badge ${message.confidence >= 0.7 ? 'success' : message.confidence >= 0.4 ? 'processing' : 'failed'}`}>
              置信度 {Math.round(message.confidence * 100)}%
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
              <span>推理链 ({message.reactSteps.length} 步)</span>
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
                title="复制"
                onClick={() => onCopy(message.content)}
              >
                <ICONS.copy size={14} />
                <span>复制</span>
              </button>
              {REFINE_ACTIONS.map((action) => (
                <button
                  key={action.id}
                  type="button"
                  className="refine-btn"
                  title={action.label}
                  onClick={() => onRefine(action.id, message.content)}
                >
                  <span>{action.label}</span>
                </button>
              ))}
              <button
                type="button"
                className="refine-btn refine-btn-danger"
                title="删除"
                onClick={() => onDelete(message.id)}
              >
                <ICONS.close size={14} />
                <span>删除</span>
              </button>
            </div>
          )}
      </div>
    </div>
  )
})

export default function AgentChatPage() {
  const location = useLocation()
  const params = new URLSearchParams(location.search)
  const initialQuestion = params.get('question') || ''

  const [messages, setMessages] = useState<Message[]>([])
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [question, setQuestion] = useState(initialQuestion)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [errorLevel, setErrorLevel] = useState<ErrorLevel>('unknown')

  /* --- function bar state --- */
  const [deepThink, setDeepThink] = useState(false)
  const [useWeb, setUseWeb] = useState(false)
  const [activeModel, setActiveModel] = useState(AVAILABLE_MODELS[0])
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
  const inputRef = useRef<HTMLInputElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const abortControllerRef = useRef<AbortController | null>(null)
  const initialSubmittedRef = useRef(false)
  const modelDropdownRef = useRef<HTMLDivElement>(null)

  /* ------------------------------------------------------------------ */
  /*  Effects                                                            */
  /* ------------------------------------------------------------------ */

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading, streamingMessageId])

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

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
      setLoading(true)
      setError('')
      setErrorLevel('unknown')
      setStreamingMessageId(null)

      const history = messages
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
            message: 'Response body is not readable — 后端未返回流式响应体',
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
                      if (event.question) {
                        /* no-op — question already shown */
                      }
                      return m

                    case 'thinking':
                      return { ...m, thinking: event.content || '' }

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
                      setError(event.message || '未知错误')
                      // 后端主动通过 SSE 上报的错误通常属于服务端错误
                      setErrorLevel('server')
                      return m

                    default:
                      return m
                  }
                }),
              )

              if (event.type === 'done') {
                setConversationId((prev) => prev) // keep existing for now
                setStreamingMessageId(null)
                // Parse reasoning chain and confidence from done payload
                if (event.payload && typeof event.payload === 'object') {
                  const payload = event.payload as Record<string, unknown>
                  const reactSteps = payload.react_steps as Array<Record<string, unknown>> | undefined
                  const confidence = typeof payload.confidence === 'number' ? payload.confidence : undefined
                  if (reactSteps || confidence != null) {
                    setMessages((prev) =>
                      prev.map((m) => {
                        if (m.id === streamingMessageId) {
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
          // user aborted — keep partial content，不上报错误
        } else {
          const msg = getErrorMessage(err, '连接中断，请稍后重试')
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
    [loading, messages, conversationId, deepThink, useWeb, activeModel, uploadedFiles],
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
          throw new Error('无法解析的命令')
        }
        const result = await parsed.command.handler(parsed.args)
        setMessages((prev) =>
          prev.map((m) => (m.id === answerId ? { ...m, content: result } : m)),
        )
      } catch (err) {
        const msg = err instanceof Error ? err.message : '命令执行失败'
        setError(msg)
        setErrorLevel(getErrorLevel(err) === 'unknown' ? 'client' : getErrorLevel(err))
        // 把空 answer 消息删掉，避免出现一个空气泡
        setMessages((prev) => prev.filter((m) => m.id !== answerId))
      } finally {
        setLoading(false)
        setStreamingMessageId(null)
      }
    },
    [role],
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

  /** 输入框键盘事件：在面板可见时，让面板接管方向键 */
  const handleInputKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
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
  }

  /** 输入框内容变化时，决定是否显示 slash 面板 */
  const handleInputChange = (e: ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value
    setQuestion(value)
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
        setError(`文件 ${f.name} 超过 50MB 限制，已跳过`)
        continue
      }
      // 读取文件内容为 base64，让后端真正解析与注入 agent 上下文
      try {
        const base64 = await readFileAsBase64(f)
        newFiles.push({ name: f.name, size: f.size, type: f.type, base64 })
      } catch (err) {
        setError(`文件 ${f.name} 读取失败：${(err as Error).message}`)
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
    } catch {
      // fallback silently
    }
  }

  const handleRefine = (action: string, msgContent: string) => {
    const prompts: Record<string, string> = {
      regenerate: `请重新回答以下问题`,
      add_details: `请为以下回答添加更多细节和深度分析`,
      more_concise: `请将以下回答压缩为更简洁的版本`,
      polish: `请润色以下回答使其更加专业流畅`,
    }
    const refinement = prompts[action] || ''
    if (refinement) {
      void handleSubmitInternal(`${refinement}：\n\n${msgContent}`)
    }
  }

  const handleDeleteMessage = (msgId: string) => {
    setMessages((prev) => prev.filter((m) => m.id !== msgId))
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
          <h1>智能分析终端</h1>
          <p className="text-muted text-sm">自然语言查询财务数据 | AI 驱动报表分析</p>
        </div>
      </div>

      <div className="card chat-container">
        <div className="chat-messages">
          {!hasContent ? (
            /* ----- Empty state ----- */
            <div className="chat-empty">
              <div className="chat-empty-glyph" aria-hidden="true">
                FA
              </div>
              <h4 className="chat-empty-title">财务智能分析</h4>
              <p className="chat-empty-desc">
                输入财务问题查询营收、利润率、负债率等关键指标，或生成分析报告。
              </p>
              <div className="chat-quick-prompts">
                {SUGGESTIONS.map((text) => (
                  <button
                    key={text}
                    type="button"
                    className="chip"
                    onClick={() => onSuggestionClick(text)}
                    disabled={loading}
                  >
                    {text}
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
            <button
              type="button"
              className="chat-error-close"
              onClick={() => {
                setError('')
                setErrorLevel('unknown')
              }}
              aria-label="关闭"
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
                  aria-label={`移除 ${f.name}`}
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
            title="深度思考"
            aria-pressed={deepThink}
          >
            <ICONS.reflections size={16} className="func-btn-icon" />
            <span>深度思考</span>
          </button>

          <button
            type="button"
            className={`func-btn ${useWeb ? 'active' : ''}`}
            onClick={() => setUseWeb((v) => !v)}
            title="联网搜索"
            aria-pressed={useWeb}
          >
            <ICONS.search size={16} className="func-btn-icon" />
            <span>联网搜索</span>
          </button>

          <button
            type="button"
            className="func-btn"
            onClick={() => fileInputRef.current?.click()}
            title="上传文件"
          >
            <ICONS.documents size={16} className="func-btn-icon" />
            <span>上传文件</span>
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
              title="切换模型"
            >
              <span className="func-btn-model-label">模型</span>
              <span className="func-btn-model-name">{activeModel.label}</span>
              <span className={`func-btn-model-chevron ${showModelDropdown ? 'open' : ''}`}>
                ▾
              </span>
            </button>
            {showModelDropdown && (
              <div className="model-dropdown">
                {AVAILABLE_MODELS.map((m) => (
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
              title="斜杠命令面板"
              aria-label="打开斜杠命令面板"
              disabled={loading}
            >
              /
            </button>
            <input
              ref={inputRef}
              className="chat-input-field"
              value={question}
              onChange={handleInputChange}
              onKeyDown={handleInputKeyDown}
              placeholder="输入问题，或输入 / 调用命令面板控制整个程序"
              disabled={loading}
              aria-label="输入问题"
            />
            <button
              type="submit"
              className="chat-send"
              disabled={loading || !question.trim()}
              aria-label="发送"
            >
              <ICONS.send size={16} />
              <span>{loading ? '发送中' : '发送'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
