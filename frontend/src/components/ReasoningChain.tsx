import type { CSSProperties } from 'react'
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

      {isNonEmpty(step.observation) && (
        <div style={{ ...toneBlockStyle('info'), marginBottom: '0.375rem' }}>
          <strong>观察：</strong>
          <span>{step.observation}</span>
        </div>
      )}

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
