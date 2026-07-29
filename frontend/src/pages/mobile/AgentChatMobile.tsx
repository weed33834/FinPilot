import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'
import i18n from '../../i18n/config.ts'
import zhCnResource from '../../i18n/locales/zh-CN/agent-chat.json'
import enResource from '../../i18n/locales/en/agent-chat.json'
import { useAgentChatStream, type ChatMessage } from '../../hooks/useAgentChatStream'
import { ICONS } from '../../components/ui/Icons'
import MarkdownRenderer from '../../components/MarkdownRenderer'
import MobilePageHeader from '../../components/mobile/MobilePageHeader'
import BottomSheet from '../../components/mobile/BottomSheet'
import '../../i18n/mobile'

// 复用 agent-chat 文案命名空间（与桌面页一致，模块内注入，不改动全局注册表）
const NS = 'agentChat'
if (!i18n.hasResourceBundle('zh-CN', NS)) {
  i18n.addResourceBundle('zh-CN', NS, zhCnResource)
}
if (!i18n.hasResourceBundle('en', NS)) {
  i18n.addResourceBundle('en', NS, enResource)
}

const SLASH_COMMANDS = ['/report', '/dashboard', '/queries', '/conversations', '/documents', '/help']

function ThinkingBlock({ message }: { message: ChatMessage }) {
  const [open, setOpen] = useState(false)
  if (!message.thinking) return null
  const time = message.thinkingTimeMs
    ? ` · ${(message.thinkingTimeMs / 1000).toFixed(1)}s`
    : ''
  return (
    <details className="mchat__thinking" open={open} onToggle={() => setOpen((v) => !v)}>
      <summary>
        <ICONS.copy size={14} />
        <span>{time ? `思考${time}` : '思考过程'}</span>
      </summary>
      <pre className="mchat__thinking-body">{message.thinking}</pre>
    </details>
  )
}

/**
 * 移动端智能对话：全屏布局、顶部标题栏、可滚动消息流、底部吸附输入栏。
 * 与桌面侧栏对话是完全不同的交互范式（无侧边会话列表、无快捷键面板）。
 */
export default function AgentChatMobile() {
  const { t } = useTranslation('agentChat')
  const { messages, loading, streaming, error, send, stop, reset } = useAgentChatStream()
  const [input, setInput] = useState('')
  const [showSlash, setShowSlash] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }, [messages])

  const handleSend = () => {
    const text = input
    if (!text.trim()) return
    setInput('')
    void send(text)
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const insertSlash = (cmd: string) => {
    setInput((v) => (v.trim() ? `${v} ${cmd} ` : `${cmd} `))
    setShowSlash(false)
  }

  return (
    <div className="mchat">
      <MobilePageHeader
        title={t('title')}
        right={
          <button
            type="button"
            className="mchat__new"
            aria-label={t('newChat')}
            onClick={reset}
          >
            <ICONS.copy size={18} />
          </button>
        }
      />

      <div className="mchat__messages" ref={scrollRef}>
        {messages.length === 0 && (
          <div className="mchat__empty">
            <ICONS.agent size={32} />
            <p>{t('empty.desc')}</p>
          </div>
        )}

        {messages.map((m) => (
          <div
            key={m.id}
            className={`mchat__row mchat__row--${m.role}`}
          >
            {m.role === 'agent' && <ThinkingBlock message={m} />}
            <div className="mchat__bubble">
              {m.role === 'agent' ? (
                m.content ? (
                  <MarkdownRenderer content={m.content} />
                ) : streaming ? (
                  <span className="mchat__typing">{t('message.thinking')}</span>
                ) : m.stopped ? (
                  <span className="mchat__stopped">{t('message.stopped')}</span>
                ) : null
              ) : (
                <span className="mchat__user-text">{m.content}</span>
              )}
            </div>
          </div>
        ))}

        {error && <div className="mchat__error">{error}</div>}
      </div>

      <div className="mchat__composer">
        <button
          type="button"
          className="mchat__slash"
          aria-label="slash commands"
          onClick={() => setShowSlash(true)}
        >
          <span>/</span>
        </button>
        <textarea
          className="mchat__input"
          value={input}
          rows={1}
          placeholder={t('input.placeholder')}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        {streaming ? (
          <button
            type="button"
            className="mchat__send mchat__send--stop"
            aria-label={t('input.stop')}
            onClick={stop}
          >
            <ICONS.stop size={18} />
          </button>
        ) : (
          <button
            type="button"
            className="mchat__send"
            aria-label={t('input.send')}
            onClick={handleSend}
            disabled={!input.trim() && !loading}
          >
            <ICONS.send size={18} />
          </button>
        )}
      </div>

      <BottomSheet open={showSlash} onClose={() => setShowSlash(false)} title={t('input.slashPaletteTitle')}>
        <div className="mchat__slash-list">
          {SLASH_COMMANDS.map((cmd) => (
            <button
              key={cmd}
              type="button"
              className="mchat__slash-item"
              onClick={() => insertSlash(cmd)}
            >
              {cmd}
            </button>
          ))}
        </div>
      </BottomSheet>
    </div>
  )
}
