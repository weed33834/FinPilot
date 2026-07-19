import { useMemo } from 'react'

interface PasswordStrengthProps {
  password: string
}

interface StrengthInfo {
  score: number // 0-4
  label: string
  color: string
  percent: number
}

function evaluate(password: string): StrengthInfo {
  if (!password) return { score: 0, label: '', color: 'transparent', percent: 0 }

  let score = 0
  if (password.length >= 8) score++
  if (password.length >= 12) score++
  if (/[A-Z]/.test(password) && /[a-z]/.test(password)) score++
  if (/\d/.test(password)) score++
  if (/[^A-Za-z0-9]/.test(password)) score++

  // cap at 4
  score = Math.min(score, 4)

  const map: Record<number, StrengthInfo> = {
    0: { score: 0, label: '太短', color: 'var(--color-danger)', percent: 20 },
    1: { score: 1, label: '弱', color: 'var(--color-danger)', percent: 40 },
    2: { score: 2, label: '一般', color: 'var(--color-warning)', percent: 60 },
    3: { score: 3, label: '较强', color: 'var(--color-info)', percent: 80 },
    4: { score: 4, label: '强', color: 'var(--color-success)', percent: 100 },
  }

  return map[score] ?? map[0]
}

export default function PasswordStrength({ password }: PasswordStrengthProps) {
  const info = useMemo(() => evaluate(password), [password])

  if (!password) return null

  return (
    <div
      style={{ marginTop: '6px' }}
      role="meter"
      aria-valuenow={info.score}
      aria-valuemin={0}
      aria-valuemax={4}
      aria-label={`密码强度: ${info.label}`}
    >
      <div
        style={{
          display: 'flex',
          gap: '3px',
          marginBottom: '2px',
        }}
      >
        {[0, 1, 2, 3].map((i) => (
          <div
            key={i}
            style={{
              flex: 1,
              height: '3px',
              borderRadius: '2px',
              background: i <= info.score ? info.color : 'var(--color-border)',
              transition: 'background 200ms ease',
            }}
          />
        ))}
      </div>
      <span
        style={{
          fontSize: '0.6875rem',
          color: info.color,
          fontWeight: 500,
        }}
      >
        {info.label}
      </span>
    </div>
  )
}
