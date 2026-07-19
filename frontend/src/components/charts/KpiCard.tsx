import { ICONS } from '../ui/Icons.tsx'
import { formatMetricValue } from '../../utils/format.ts'

interface ChangeTuple {
  value: number | null
  change: number | null
  change_pct: number | null
}

interface SparkPoint {
  period: string
  value: number
}

interface KpiCardProps {
  label: string
  value: number | null
  unit: string
  yoy?: ChangeTuple | null
  qoq?: ChangeTuple | null
  spark?: SparkPoint[] | null
  loading?: boolean
  active?: boolean
  onClick?: () => void
}

interface ChangeBadgeProps {
  change: ChangeTuple | null | undefined
  caption: string
}

function ChangeBadge({ change, caption }: ChangeBadgeProps) {
  if (!change || change.change_pct === null || change.change_pct === undefined) {
    return (
      <span className="kpi-change muted" data-testid={`kpi-change-${caption}`}>
        {caption} —
      </span>
    )
  }
  const pct = change.change_pct
  const cls = pct > 0 ? 'up' : pct < 0 ? 'down' : 'muted'
  const arrow = pct > 0 ? '↑' : pct < 0 ? '↓' : '→'
  const text = pct === 0 ? '0.00%' : `${arrow} ${Math.abs(pct).toFixed(2)}%`
  return (
    <span className={`kpi-change ${cls}`} data-testid={`kpi-change-${caption}`}>
      {caption} {text}
    </span>
  )
}

function SparkBars({ data }: { data: SparkPoint[] | null | undefined }) {
  if (!data || data.length === 0) return null
  const max = Math.max(...data.map((d) => d.value), 0)
  const min = Math.min(...data.map((d) => d.value), 0)
  const range = Math.max(max - min, 1)
  return (
    <div className="kpi-spark" aria-hidden="true">
      {data.slice(-8).map((d, i) => {
        const ratio = (d.value - min) / range
        return (
          <span
            key={`${d.period}-${i}`}
            className="kpi-spark-bar"
            style={{ height: `${Math.max(ratio * 100, 8)}%` }}
            title={`${d.period}: ${d.value}`}
          />
        )
      })}
    </div>
  )
}

export default function KpiCard({
  label,
  value,
  unit,
  yoy,
  qoq,
  spark,
  loading,
  active,
  onClick,
}: KpiCardProps) {
  const clickable = Boolean(onClick)
  const className = `kpi-card${active ? ' active' : ''}${clickable ? ' clickable' : ''}`
  const content = (
    <>
      <div className="kpi-card-label">
        <span>{label}</span>
        {clickable && !loading && (
          <ICONS.trend size={14} className="kpi-card-drill" aria-hidden="true" />
        )}
      </div>
      {loading ? (
        <div className="kpi-card-value" role="status" aria-label="加载中">
          加载中…
        </div>
      ) : value !== null && value !== undefined ? (
        <>
          <div className="kpi-card-value">{formatMetricValue(value, unit)}</div>
          <SparkBars data={spark} />
          <div className="kpi-card-changes">
            <ChangeBadge change={yoy} caption="同比" />
            <ChangeBadge change={qoq} caption="环比" />
          </div>
        </>
      ) : (
        <>
          <div className="kpi-card-value kpi-empty">—</div>
          <div className="kpi-card-changes">
            <span className="kpi-change muted">暂无数据</span>
          </div>
        </>
      )}
    </>
  )

  if (!clickable) {
    return (
      <div className={className} data-testid="kpi-card">
        {content}
      </div>
    )
  }

  return (
    <div
      className={className}
      role="button"
      tabIndex={0}
      data-testid="kpi-card"
      aria-pressed={active}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onClick?.()
        }
      }}
    >
      {content}
    </div>
  )
}
