import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import i18n from '../../i18n/config.ts'
import zhCnResource from '../../i18n/locales/zh-CN/admin-dashboard.json'
import enResource from '../../i18n/locales/en/admin-dashboard.json'
import { adminApi } from '../../api/adminClient.ts'
import Loading from '../../components/ui/Loading.tsx'
import EmptyState from '../../components/ui/EmptyState.tsx'
import { ICONS } from '../../components/ui/Icons.tsx'
import { getErrorMessage } from '../../utils/errors.ts'
import { formatDateTime } from '../../utils/format.ts'
import { getHealthCheck } from '../../api/settings.ts'
import type { ApiResponse } from '../../api/types.ts'

// 命名空间未在 i18n/config.ts 中注册（按要求不修改该文件），这里在模块加载时
// 同步注入资源，组件通过 useTranslation('adminDashboard') 消费。
const NS = 'adminDashboard'
if (!i18n.hasResourceBundle('zh-CN', NS)) {
  i18n.addResourceBundle('zh-CN', NS, zhCnResource)
}
if (!i18n.hasResourceBundle('en', NS)) {
  i18n.addResourceBundle('en', NS, enResource)
}

interface DashboardStats {
  models: { total: number; active: number; default: string }
  prompts: { total: number; active: number }
  tools: { total: number; active: number; builtin: number; custom: number }
  skills: { total: number; active: number }
  agents: { total: number; active: number }
  search_engines: { total: number; active: number; default: string }
  conversations: { total: number; today: number }
  system_health: { status: string; uptime_hours: number }
  recent_conversations: Array<{ id: string; title: string; created_at: string | null }>
}

function StatusIndicator({ status }: { status: string | undefined }) {
  const color =
    status === 'connected' || status === 'available' || status === 'ready' || status === 'healthy'
      ? '#22c55e'
      : status === 'degraded' || status === 'unconfigured'
        ? '#f59e0b'
        : '#ef4444'
  return <span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: '50%', backgroundColor: color, marginRight: 8 }} />
}

interface StatCardProps {
  icon: React.ReactNode
  iconVariant: string
  value: string
  label: string
  hint?: string
}

function StatCard({ icon, iconVariant, value, label, hint }: StatCardProps) {
  return (
    <div className="stat-card">
      <div className="stat-card-head">
        <div className={`stat-icon ${iconVariant}`}>{icon}</div>
      </div>
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
      {hint && <div className="stat-hint">{hint}</div>}
    </div>
  )
}

export default function Dashboard() {
  const { t } = useTranslation('adminDashboard')

  const { data, isLoading, isError, error, isFetching, refetch } = useQuery({
    queryKey: ['adminDashboard'],
    queryFn: async () => {
      const [statsRes, healthRes] = await Promise.all([
        adminApi.get<ApiResponse<DashboardStats>>('/dashboard/admin/stats'),
        getHealthCheck(),
      ])
      return {
        stats: statsRes.data.data,
        health: healthRes.data.data,
      }
    },
    refetchInterval: 30000,
    retry: 1,
  })

  if (isLoading) return <Loading text={t('loading')} />
  if (isError && !data) {
    return (
      <EmptyState
        title={t('errors.loadFailed')}
        description={getErrorMessage(error, t('errors.loadFailed'))}
        icon="empty"
        action={
          <button type="button" className="btn btn-secondary" onClick={() => refetch()}>
            <ICONS.refresh size={14} />
            {t('actions.retry')}
          </button>
        }
      />
    )
  }

  const stats = data?.stats
  const health = data?.health

  const statCards = [
    {
      icon: <ICONS.llm size={20} />,
      iconVariant: 'reports',
      label: t('statCards.models.label'),
      value: `${stats?.models.active ?? 0} / ${stats?.models.total ?? 0}`,
      hint: t('statCards.models.sub', { name: stats?.models.default || '—' }),
    },
    {
      icon: <ICONS.agent size={20} />,
      iconVariant: 'agent',
      label: t('statCards.conversations.label'),
      value: `${stats?.conversations.today ?? 0} / ${stats?.conversations.total ?? 0}`,
      hint: t('statCards.conversations.sub'),
    },
    {
      icon: <ICONS.settings size={20} />,
      iconVariant: 'documents',
      label: t('statCards.tools.label'),
      value: `${stats?.tools.active ?? 0} / ${stats?.tools.total ?? 0}`,
      hint: t('statCards.tools.sub', {
        builtin: stats?.tools.builtin ?? 0,
        custom: stats?.tools.custom ?? 0,
      }),
    },
    {
      icon: <ICONS.audit size={20} />,
      iconVariant: 'approvals',
      label: t('statCards.system.label'),
      value:
        stats?.system_health.status === 'healthy' ? t('status.healthy') : t('status.degraded'),
    },
  ]

  const healthRows = [
    { name: t('health.components.database'), item: health?.database },
    { name: t('health.components.vectorStore'), item: health?.vector_store },
    {
      name: t('health.components.llm'),
      item: health?.default_llm,
      extra: health?.default_llm.model_name,
    },
    { name: t('health.components.sandbox'), item: health?.sandbox },
    {
      name: t('health.components.searchEngines'),
      item: {
        status: health?.search_engines.active ? 'available' : 'unconfigured',
        latency_ms: 0,
      },
      extra: `${health?.search_engines.active ?? 0} ${t('health.active')}`,
    },
  ]

  const recent = stats?.recent_conversations ?? []

  return (
    <div>
      {/* 页头 */}
      <div
        className="admin-page-header"
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          gap: 12,
          flexWrap: 'wrap',
        }}
      >
        <div>
          <h1 className="admin-page-title">{t('title')}</h1>
          <p className="admin-page-subtitle">{t('subtitle')}</p>
        </div>
        <div className="admin-actions">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => refetch()}
            disabled={isFetching}
            title={t('actions.refresh')}
          >
            <ICONS.refresh size={14} />
            {t('actions.refresh')}
          </button>
        </div>
      </div>

      {/* Stat Cards */}
      <div className="stat-grid">
        {statCards.map((card) => (
          <StatCard
            key={card.label}
            icon={card.icon}
            iconVariant={card.iconVariant}
            value={card.value}
            label={card.label}
            hint={card.hint}
          />
        ))}
      </div>

      {/* Health Panel */}
      <div className="card">
        <h3 className="card-title">{t('health.title')}</h3>
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>{t('health.table.component')}</th>
                <th>{t('health.table.status')}</th>
                <th>{t('health.table.latency')}</th>
                <th>{t('health.table.detail')}</th>
              </tr>
            </thead>
            <tbody>
              {healthRows.map((row) => (
                <tr key={row.name}>
                  <td>{row.name}</td>
                  <td>
                    <StatusIndicator status={row.item?.status} />
                    {row.item?.status ?? '—'}
                  </td>
                  <td>
                    {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                    {(row.item as any)?.latency_ms ? `${(row.item as any).latency_ms}ms` : '—'}
                  </td>
                  <td>
                    {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                    {row.extra || (row.item as any)?.message || '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {health?.timestamp && (
          <div className="text-muted" style={{ fontSize: '0.75rem', marginTop: 'var(--space-3)' }}>
            {t('health.checkedAt', { time: formatDateTime(health.timestamp) })}
          </div>
        )}
      </div>

      {/* Recent Conversations */}
      <div className="card">
        <h3 className="card-title">{t('recent.title')}</h3>
        {recent.length ? (
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>{t('recent.table.title')}</th>
                  <th>{t('recent.table.time')}</th>
                </tr>
              </thead>
              <tbody>
                {recent.map((c) => (
                  <tr key={c.id}>
                    <td>{c.title || t('recent.unnamed')}</td>
                    <td>{formatDateTime(c.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState title={t('recent.empty')} />
        )}
      </div>
    </div>
  )
}
