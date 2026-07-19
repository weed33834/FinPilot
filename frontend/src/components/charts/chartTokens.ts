// recharts 图表共享样式令牌，集中维护避免多处重复定义

export const CHART_AXIS_TICK = {
  fontSize: 12,
  fill: 'var(--color-text-secondary)',
} as const

export const CHART_AXIS_PROPS = {
  axisLine: false,
  tickLine: false,
} as const

export const CHART_GRID_PROPS = {
  strokeDasharray: '3 3',
  vertical: false,
  stroke: 'var(--color-border-light)',
} as const

export const CHART_TOOLTIP_STYLE = {
  background: 'var(--color-surface)',
  border: '1px solid var(--color-border)',
  borderRadius: 'var(--radius-md)',
  fontSize: 'var(--text-sm)',
  fontFamily: 'var(--font-sans)',
  boxShadow: 'var(--shadow-md)',
  padding: 'var(--space-2) var(--space-3)',
} as const

export const CHART_LABEL_STYLE = {
  color: 'var(--color-text-secondary)',
  fontSize: 'var(--text-xs)',
  marginBottom: '2px',
} as const

export const CHART_COLORS = [
  'var(--color-primary)',
  'var(--color-success)',
  'var(--color-warning)',
  'var(--color-info)',
  'var(--color-purple)',
  'var(--color-danger)',
  'var(--color-text-secondary)',
] as const
