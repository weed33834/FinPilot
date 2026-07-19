import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ICONS } from '../../components/ui/Icons.tsx'
import {
  CHART_TOOLTIP_STYLE,
  CHART_LABEL_STYLE,
  CHART_AXIS_TICK,
  CHART_AXIS_PROPS,
  CHART_GRID_PROPS,
} from '../../components/charts/chartTokens.ts'
import {
  BarChart,
  Bar,
  CartesianGrid,
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip as ReTooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { DashboardSummary } from './constants.ts'

export interface ChartDatum {
  name: string
  value: number
  color: string
}

interface ReportTrendChartProps {
  trend: DashboardSummary['approval_trend']
}

export function ReportTrendChart({ trend }: ReportTrendChartProps) {
  const { t } = useTranslation(['common', 'dashboard'])
  const total = trend.reduce((sum, item) => sum + (item.count || 0), 0)
  return (
    <div className="card card-wide">
      <div className="dashboard-card-head">
        <div>
          <h3 className="card-title">{t('dashboard:sections.reportTrend')}</h3>
          <span className="card-meta">{t('dashboard:meta.last7d') || '近 7 天'}</span>
        </div>
        <div className="card-stat-inline">
          <span className="card-stat-num">{total}</span>
          <span className="card-stat-label">{t('dashboard:meta.total') || '总数'}</span>
        </div>
      </div>
      {trend.length === 0 || total === 0 ? (
        <div className="empty-state">
          <ICONS.trend size={40} className="empty-state-icon" />
          <p className="empty-state-title">{t('dashboard:empty.reportTrend')}</p>
          <p className="empty-state-desc">{t('dashboard:empty.reportTrendDesc') || '尚无审批数据，开始创建报告后趋势会出现在这里'}</p>
        </div>
      ) : (
        <div className="chart-container chart-container-lg">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={trend} margin={{ top: 8, right: 16, bottom: 8, left: -16 }}>
              <CartesianGrid {...CHART_GRID_PROPS} />
              <XAxis dataKey="date" tick={CHART_AXIS_TICK} {...CHART_AXIS_PROPS} />
              <YAxis allowDecimals={false} tick={CHART_AXIS_TICK} {...CHART_AXIS_PROPS} />
              <ReTooltip contentStyle={CHART_TOOLTIP_STYLE} labelStyle={CHART_LABEL_STYLE} cursor={{ fill: 'var(--color-primary-subtle)' }} />
              <Bar dataKey="count" fill="var(--color-primary)" radius={[6, 6, 0, 0]} maxBarSize={48} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}

interface PendingTodoCardProps {
  count: number
}

export function PendingTodoCard({ count }: PendingTodoCardProps) {
  const { t } = useTranslation(['common', 'dashboard'])
  return (
    <div className={`card ${count > 0 ? 'card-accent-warning' : ''}`}>
      <div className="dashboard-card-head">
        <h3 className="card-title">{t('dashboard:sections.pendingTodo')}</h3>
        <ICONS.approvals size={18} className="dashboard-card-icon" />
      </div>
      <div className="approval-summary">
        <div className={`approval-count ${count === 0 ? 'is-zero' : ''}`}>{count}</div>
        <div className="approval-desc">
          {count === 0 ? t('dashboard:empty.pendingTodo') : t('dashboard:pendingReview', { count })}
        </div>
        {count > 0 && (
          <Link to="/approvals" className="btn btn-primary mt-3">
            <ICONS.approvals size={14} />
            {t('dashboard:actions.process')}
          </Link>
        )}
        {count === 0 && (
          <div className="empty-hint">{t('dashboard:empty.pendingTodoHint') || '无待办工作 · 一切井然有序'}</div>
        )}
      </div>
    </div>
  )
}

interface StatusDistributionChartProps {
  title: string
  data: ChartDatum[]
  /** 用于 Pie Cell key 去重，避免不同卡片同 index 冲突 */
  cellKeyPrefix: string
}

export function StatusDistributionChart({ title, data, cellKeyPrefix }: StatusDistributionChartProps) {
  const { t } = useTranslation('common')
  return (
    <div className="card">
      <div className="dashboard-card-head">
        <h3 className="card-title">{title}</h3>
        <span className="card-meta">{data.reduce((s, d) => s + d.value, 0)} {t('common:units.total') || '条'}</span>
      </div>
      {data.length === 0 ? (
        <div className="empty-state empty-state-sm">
          <ICONS.trend size={32} className="empty-state-icon" />
          <p className="empty-state-title">{t('status.empty')}</p>
        </div>
      ) : (
        <>
          <div className="chart-container">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={data}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  innerRadius={55}
                  outerRadius={78}
                  paddingAngle={2}
                >
                  {data.map((entry, index) => (
                    <Cell key={`${cellKeyPrefix}-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <ReTooltip contentStyle={CHART_TOOLTIP_STYLE} labelStyle={CHART_LABEL_STYLE} />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="legend">
            {data.map((item) => (
              <div key={item.name} className="legend-item">
                <span className="legend-dot" style={{ background: item.color }} />
                <span>
                  {item.name}: <strong>{item.value}</strong>
                </span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
