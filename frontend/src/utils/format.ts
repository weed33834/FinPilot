/** 日期时间格式化：年-月-日 时:分（如「2026-07-15 14:30」） */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const d = new Date(value)
  if (isNaN(d.getTime())) return '—'
  return d.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** 仅日期格式化：年-月-日（如「2026-07-15」） */
export function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  const d = new Date(value)
  if (isNaN(d.getTime())) return '—'
  return d.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  })
}

/** 数值千分位格式化（图表轴刻度用） */
export function formatTick(value: number): string {
  return value.toLocaleString('zh-CN', { maximumFractionDigits: 0 })
}

/** 指标值格式化：null →「—」，百分比 →「12.34%」，其余千分位 */
export function formatMetricValue(v: number | null, unit: string): string {
  if (v === null || v === undefined) return '—'
  if (unit === '%') return `${(v * 100).toFixed(2)}%`
  return v.toLocaleString('zh-CN', { maximumFractionDigits: 0 })
}
