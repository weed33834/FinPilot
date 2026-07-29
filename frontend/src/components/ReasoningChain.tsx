import type { CSSProperties } from 'react'
import { useState } from 'react'
import EmptyState from './ui/EmptyState.tsx'

export interface ReasoningStep {
  step?: string
  thought?: string
  action?: string
  action_input?: string
  observation?: string
  result?: string
  error?: string
  confidence?: number
}

interface ReasoningChainProps {
  steps: ReasoningStep[]
  confidence?: number
}

type Tone = 'success' | 'error' | 'info'

/**
 * 复用现有 .badge 变体以保持颜色一致：
 * - success → 绿色（badge.success）
 * - error   → 红色（badge.failed）
 * - info    → 蓝色（badge.processing）
 */
const TONE_BADGE_CLASS: Record<Tone, string> = {
  success: 'badge success',
  error: 'badge failed',
  info: 'badge processing',
}

const TONE_ACCENT: Record<Tone, string> = {
  success: 'var(--color-success)',
  error: 'var(--color-danger)',
  info: 'var(--color-info)',
}

const TONE_TEXT: Record<Tone, string> = {
  success: 'var(--color-success)',
  error: 'var(--color-danger)',
  info: 'var(--color-info)',
}

const TONE_BG: Record<Tone, string> = {
  success: 'var(--color-success-subtle)',
  error: 'var(--color-danger-subtle)',
  info: 'var(--color-info-subtle)',
}

function getStepTone(step: ReasoningStep): Tone {
  if (step.error) return 'error'
  if (step.result || step.observation) return 'success'
  return 'info'
}

function toneBlockStyle(tone: Tone): CSSProperties {
  return {
    color: TONE_TEXT[tone],
    background: TONE_BG[tone],
    border: `1px solid ${TONE_ACCENT[tone]}`,
    borderRadius: 'var(--radius-sm)',
    padding: '0.5rem 0.75rem',
    fontSize: '0.8125rem',
    lineHeight: 1.5,
    wordBreak: 'break-word',
  }
}

/**
 * 置信度支持 0-1 区间或 0-100 百分比：
 * 值 <= 1 视为比例（乘以 100），否则视为已为百分比。
 */
function toPercent(value: number): number {
  return value <= 1 ? value * 100 : value
}

function formatConfidence(value: number): string {
  return `${Math.round(toPercent(value))}%`
}

function confidenceBadgeClass(confidence: number): string {
  const pct = toPercent(confidence)
  if (pct >= 80) return 'badge success'
  if (pct >= 50) return 'badge processing'
  return 'badge modify'
}

function getStepNumber(step: ReasoningStep, index: number): string {
  if (step.step !== undefined && step.step !== '') return step.step
  return String(index + 1)
}

function isNonEmpty(value: string | undefined): value is string {
  return value !== undefined && value !== null && value !== ''
}

interface WebSearchResultItem {
  title?: string
  url?: string
  snippet?: string
}

interface WebSearchObservation {
  query?: string
  engine?: string
  result_count?: number
  results?: WebSearchResultItem[]
  summary?: string
  error?: string
}

/**
 * web_search 工具的 observation 可视化：解析 JSON 后渲染可折叠的引用来源卡片，
 * 包含序号、标题（点击跳转新标签页）、URL、摘要。解析失败回退为带"观察："标签的纯文本。
 */
function WebSearchResults({ raw }: { raw: string }) {
  const [expanded, setExpanded] = useState(true)

  let data: WebSearchObservation | null = null
  if (raw) {
    try {
      const parsed = JSON.parse(raw)
      if (parsed && typeof parsed === 'object') data = parsed as WebSearchObservation
    } catch {
      data = null
    }
  }

  // 解析失败：回退为与原 observation 块一致的纯文本展示
  if (!data) {
    return (
      <div style={{ ...toneBlockStyle('info'), marginBottom: '0.375rem' }}>
        <strong>观察：</strong>
        <span style={{ whiteSpace: 'pre-wrap' }}>{raw}</span>
      </div>
    )
  }

  // 搜索失败分支
  if (data.error) {
    return (
      <div style={{ ...toneBlockStyle('error'), marginBottom: '0.375rem' }}>
        <strong>搜索失败：</strong>
        <span>{data.error}</span>
      </div>
    )
  }

  const results = Array.isArray(data.results) ? data.results : []
  const query = data.query || ''
  const count = data.result_count ?? results.length

  return (
    <div
      style={{
        marginBottom: '0.375rem',
        border: `1px solid ${TONE_ACCENT.info}`,
        borderRadius: 'var(--radius-sm)',
        background: TONE_BG.info,
        overflow: 'hidden',
      }}
    >
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '0.5rem',
          padding: '0.5rem 0.75rem',
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          color: TONE_TEXT.info,
          fontSize: '0.8125rem',
          fontWeight: 600,
          textAlign: 'left',
        }}
      >
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>
          🌐 联网搜索{query ? `：${query}` : ''} · 共 {count} 条结果
        </span>
        <span
          aria-hidden="true"
          style={{
            transition: 'transform 0.15s',
            transform: expanded ? 'rotate(90deg)' : 'rotate(0deg)',
            flexShrink: 0,
          }}
        >
          ▶
        </span>
      </button>
      {expanded && (
        <>
          {results.length > 0 ? (
            <ol style={{ listStyle: 'none', margin: 0, padding: '0.25rem 0.75rem 0.5rem' }}>
              {results.map((r, i) => (
                <li
                  key={`search-result-${i}`}
                  style={{
                    padding: '0.375rem 0',
                    borderBottom: i < results.length - 1 ? '1px solid var(--color-border)' : 'none',
                  }}
                >
                  <div style={{ display: 'flex', gap: '0.375rem', alignItems: 'baseline' }}>
                    <span
                      style={{
                        color: 'var(--color-text-muted)',
                        fontSize: '0.75rem',
                        minWidth: '1.25rem',
                        flexShrink: 0,
                      }}
                    >
                      {i + 1}.
                    </span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      {r.url ? (
                        <a
                          href={r.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{
                            color: TONE_TEXT.info,
                            fontWeight: 500,
                            textDecoration: 'none',
                            wordBreak: 'break-word',
                          }}
                        >
                          {r.title || r.url}
                        </a>
                      ) : (
                        <span style={{ fontWeight: 500 }}>{r.title || '(无标题)'}</span>
                      )}
                      {r.url && (
                        <div
                          style={{
                            fontSize: '0.6875rem',
                            color: 'var(--color-text-muted)',
                            marginTop: '0.125rem',
                            wordBreak: 'break-all',
                          }}
                        >
                          {r.url}
                        </div>
                      )}
                      {r.snippet && (
                        <p
                          style={{
                            margin: '0.25rem 0 0',
                            fontSize: '0.75rem',
                            color: 'var(--color-text)',
                            lineHeight: 1.5,
                            opacity: 0.85,
                          }}
                        >
                          {r.snippet}
                        </p>
                      )}
                    </div>
                  </div>
                </li>
              ))}
            </ol>
          ) : (
            <div
              style={{
                padding: '0.5rem 0.75rem',
                fontSize: '0.75rem',
                color: 'var(--color-text-muted)',
              }}
            >
              搜索未返回结果
            </div>
          )}
        </>
      )}
    </div>
  )
}

interface ReasoningStepItemProps {
  step: ReasoningStep
  index: number
  isLast: boolean
}

function ReasoningStepItem({ step, index, isLast }: ReasoningStepItemProps) {
  const tone = getStepTone(step)
  const accentColor = TONE_ACCENT[tone]
  const number = getStepNumber(step, index)
  const hasConfidence = step.confidence !== undefined && step.confidence !== null

  return (
    <li
      className="reasoning-step"
      style={{
        position: 'relative',
        paddingLeft: '2rem',
        paddingBottom: '1rem',
      }}
    >
      {/* 时间轴竖向连接线 */}
      {!isLast && (
        <span
          aria-hidden="true"
          style={{
            position: 'absolute',
            left: '0.4375rem',
            top: '1.5rem',
            bottom: 0,
            width: '2px',
            background: 'var(--color-border)',
          }}
        />
      )}
      {/* 时间轴节点圆点 */}
      <span
        aria-hidden="true"
        style={{
          position: 'absolute',
          left: 0,
          top: '0.4rem',
          width: '0.875rem',
          height: '0.875rem',
          borderRadius: '50%',
          background: accentColor,
          border: '2px solid var(--color-surface)',
        }}
      />

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
          flexWrap: 'wrap',
          marginBottom: '0.5rem',
        }}
      >
        <span className={TONE_BADGE_CLASS[tone]}>步骤 {number}</span>
        {isNonEmpty(step.action) && (
          <span className={TONE_BADGE_CLASS.info}>{step.action}</span>
        )}
        {hasConfidence && (
          <span className={confidenceBadgeClass(step.confidence as number)}>
            置信度 {formatConfidence(step.confidence as number)}
          </span>
        )}
      </div>

      {isNonEmpty(step.thought) && (
        <p
          style={{
            margin: '0 0 0.5rem',
            color: 'var(--color-text)',
            lineHeight: 1.6,
          }}
        >
          {step.thought}
        </p>
      )}

      {isNonEmpty(step.action_input) && (
        <pre
          className="code-block"
          style={{ margin: '0 0 0.5rem', whiteSpace: 'pre-wrap' }}
        >
          {step.action_input}
        </pre>
      )}

      {isNonEmpty(step.observation) &&
        (step.action === 'web_search' ? (
          <WebSearchResults raw={step.observation} />
        ) : (
          <div style={{ ...toneBlockStyle('info'), marginBottom: '0.375rem' }}>
            <strong>观察：</strong>
            <span style={{ whiteSpace: 'pre-wrap' }}>{step.observation}</span>
          </div>
        ))}

      {isNonEmpty(step.result) && (
        <div style={{ ...toneBlockStyle('success'), marginBottom: '0.375rem' }}>
          <strong>结果：</strong>
          <span>{step.result}</span>
        </div>
      )}

      {isNonEmpty(step.error) && (
        <div style={{ ...toneBlockStyle('error'), marginBottom: '0.375rem' }}>
          <strong>错误：</strong>
          <span>{step.error}</span>
        </div>
      )}
    </li>
  )
}

/**
 * 推理链可视化组件
 * 以纵向时间轴形式展示智能体的 思考 → 行动 → 观察 步骤序列，
 * 含颜色编码（成功=绿、错误=红、信息=蓝）与置信度徽标。
 */
export default function ReasoningChain({ steps, confidence }: ReasoningChainProps) {
  const hasSteps = steps.length > 0
  const hasOverallConfidence = confidence !== undefined && confidence !== null

  return (
    <div className="card">
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '0.5rem',
          margin: '0 0 0.75rem',
          paddingBottom: '0.5rem',
          borderBottom: '1px solid var(--color-border)',
        }}
      >
        <h3 className="card-title" style={{ margin: 0 }}>
          推理链
        </h3>
        {hasOverallConfidence && (
          <span className={confidenceBadgeClass(confidence as number)}>
            总置信度 {formatConfidence(confidence as number)}
          </span>
        )}
      </div>

      {hasSteps ? (
        <ol
          style={{
            listStyle: 'none',
            margin: 0,
            padding: 0,
          }}
        >
          {steps.map((step, index) => (
            <ReasoningStepItem
              key={`reasoning-step-${index}`}
              step={step}
              index={index}
              isLast={index === steps.length - 1}
            />
          ))}
        </ol>
      ) : (
        <EmptyState
          title="暂无推理步骤"
          description="智能体尚未产生任何思考与行动记录。"
          icon="agent"
        />
      )}
    </div>
  )
}
