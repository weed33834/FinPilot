import { useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import { ICONS } from '../../components/ui/Icons.tsx'
import Loading from '../../components/ui/Loading.tsx'
import { toast } from '../../components/ui/Toaster.tsx'
import { getErrorMessage } from '../../utils/errors.ts'
import { formatDateTime } from '../../utils/format.ts'
import {
  getSettings,
  updateSettings,
  getHealthCheck,
  type SystemSettingsData,
  type HealthStatus,
} from '../../api/settings.ts'
import { adminApi } from '../../api/adminClient.ts'

interface SelectOption {
  id: string
  name?: string
  model_name?: string
}

// 把后端返回的健康状态原值映射为本地化文案，未知值原样返回。
// 颜色判定仍基于原始 status，与此处的文案映射相互独立。
function formatHealthStatus(status: string, t: TFunction): string {
  const s = status.toLowerCase()
  if (['connected', 'available', 'ready', 'healthy', 'ok'].includes(s)) {
    return t('health.status.healthy')
  }
  if (s === 'degraded') return t('health.status.degraded')
  if (s === 'unconfigured') return t('health.status.unconfigured')
  if (['unavailable', 'error', 'down', 'failed'].includes(s)) {
    return t('health.status.unhealthy')
  }
  if (s === 'unknown') return t('health.status.unknown')
  return status
}

export default function SystemSettings() {
  const { t } = useTranslation('adminSettings')
  const queryClient = useQueryClient()

  const form = useForm<SystemSettingsData>({
    defaultValues: {
      system_name: 'FinPilot',
      system_description: 'AI-powered financial analysis assistant',
      default_model_id: '',
      default_search_engine_id: '',
      max_conversation_history: 50,
      session_timeout_minutes: 60,
      rate_limit_per_minute: 60,
      log_level: 'INFO',
      enable_telemetry: false,
      sandbox_mode: 'lightweight',
      max_file_upload_mb: 10,
    },
  })

  const { data: settingsData, isLoading } = useQuery({
    queryKey: ['systemSettings'],
    queryFn: async () => {
      const res = await getSettings()
      return res.data.data
    },
  })

  const { data: modelsData } = useQuery({
    queryKey: ['modelConfigsForSettings'],
    queryFn: async () => {
      const res = await adminApi.get('/model-configs', { params: { page_size: 100 } })
      return (res.data?.data?.items ?? []) as SelectOption[]
    },
    staleTime: 60000,
  })

  const { data: seData } = useQuery({
    queryKey: ['searchEnginesForSettings'],
    queryFn: async () => {
      const res = await adminApi.get('/search-engines', { params: { page_size: 100 } })
      return (res.data?.data?.items ?? []) as SelectOption[]
    },
    staleTime: 60000,
  })

  const {
    data: health,
    isLoading: healthLoading,
    isFetching: healthFetching,
    error: healthError,
    refetch: refetchHealth,
  } = useQuery<HealthStatus>({
    queryKey: ['systemHealth'],
    queryFn: async () => {
      const res = await getHealthCheck()
      return res.data.data
    },
    refetchInterval: 30000, // 30s 自动刷新
    retry: 1,
  })

  useEffect(() => {
    if (settingsData) {
      form.reset({
        system_name: settingsData.system_name ?? 'FinPilot',
        system_description: settingsData.system_description ?? 'AI-powered financial analysis assistant',
        default_model_id: settingsData.default_model_id ?? '',
        default_search_engine_id: settingsData.default_search_engine_id ?? '',
        max_conversation_history: settingsData.max_conversation_history ?? 50,
        session_timeout_minutes: settingsData.session_timeout_minutes ?? 60,
        rate_limit_per_minute: settingsData.rate_limit_per_minute ?? 60,
        log_level: settingsData.log_level ?? 'INFO',
        enable_telemetry: settingsData.enable_telemetry ?? false,
        sandbox_mode: settingsData.sandbox_mode ?? 'lightweight',
        max_file_upload_mb: settingsData.max_file_upload_mb ?? 10,
      })
    }
  }, [settingsData, form])

  const updateMut = useMutation({
    mutationFn: (payload: Record<string, unknown>) => updateSettings(payload as any),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['systemSettings'] })
      toast.success(t('toast.saved.title'), t('toast.saved.description'))
    },
    onError: (err) => {
      toast.error(getErrorMessage(err, t('errors.saveFailed')))
    },
  })

  function handleReset() {
    if (settingsData) {
      form.reset({
        system_name: settingsData.system_name ?? 'FinPilot',
        system_description: settingsData.system_description ?? 'AI-powered financial analysis assistant',
        default_model_id: settingsData.default_model_id ?? '',
        default_search_engine_id: settingsData.default_search_engine_id ?? '',
        max_conversation_history: settingsData.max_conversation_history ?? 50,
        session_timeout_minutes: settingsData.session_timeout_minutes ?? 60,
        rate_limit_per_minute: settingsData.rate_limit_per_minute ?? 60,
        log_level: settingsData.log_level ?? 'INFO',
        enable_telemetry: settingsData.enable_telemetry ?? false,
        sandbox_mode: settingsData.sandbox_mode ?? 'lightweight',
        max_file_upload_mb: settingsData.max_file_upload_mb ?? 10,
      })
    }
  }

  function onSubmit(values: SystemSettingsData) {
    const payload: Record<string, unknown> = {}
    if (settingsData) {
      for (const key of Object.keys(values) as (keyof SystemSettingsData)[]) {
        if (values[key] !== settingsData[key]) {
          payload[key] = values[key]
        }
      }
    }
    if (Object.keys(payload).length === 0) return
    updateMut.mutate(payload)
  }

  if (isLoading) {
    return (
      <div style={{ padding: 24 }}>
        <Loading text={t('loading')} />
      </div>
    )
  }

  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0 }}>{t('title')}</h1>
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={handleReset} style={btnSecondaryStyle}>{t('actions.reset')}</button>
          <button
            onClick={form.handleSubmit(onSubmit)}
            disabled={updateMut.isPending}
            style={btnPrimaryStyle}
          >
            {updateMut.isPending ? t('actions.saving') : t('actions.save')}
          </button>
        </div>
      </div>

      <form onSubmit={form.handleSubmit(onSubmit)}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>

          {/* 通用设置 */}
          <SettingsCard title={t('sections.general')} icon={<ICONS.settings size={18} />}>
            <FormField label={t('fields.systemName')}>
              <input {...form.register('system_name')} style={inputStyle} />
            </FormField>
            <FormField label={t('fields.systemDescription')}>
              <textarea {...form.register('system_description')} style={{ ...inputStyle, minHeight: 60 }} />
            </FormField>
          </SettingsCard>

          {/* LLM 设置 */}
          <SettingsCard title={t('sections.llm')} icon={<ICONS.llm size={18} />}>
            <FormField label={t('fields.defaultModel')}>
              <select {...form.register('default_model_id')} style={selectStyle}>
                <option value="">{t('fields.notSet')}</option>
                {(modelsData ?? []).map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.model_name || m.name || m.id}
                  </option>
                ))}
              </select>
            </FormField>
          </SettingsCard>

          {/* 搜索设置 */}
          <SettingsCard title={t('sections.search')} icon={<ICONS.search size={18} />}>
            <FormField label={t('fields.defaultSearchEngine')}>
              <select {...form.register('default_search_engine_id')} style={selectStyle}>
                <option value="">{t('fields.notSet')}</option>
                {(seData ?? []).map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name || s.id}
                  </option>
                ))}
              </select>
            </FormField>
          </SettingsCard>

          {/* 会话设置 */}
          <SettingsCard title={t('sections.session')} icon={<ICONS.agent size={18} />}>
            <FormField label={t('fields.maxConversationHistory')}>
              <input type="number" {...form.register('max_conversation_history', { valueAsNumber: true })} style={inputStyle} min={1} max={1000} />
            </FormField>
            <FormField label={t('fields.sessionTimeout')}>
              <input type="number" {...form.register('session_timeout_minutes', { valueAsNumber: true })} style={inputStyle} min={5} max={1440} />
            </FormField>
          </SettingsCard>

          {/* 安全设置 */}
          <SettingsCard title={t('sections.security')} icon={<ICONS.security size={18} />}>
            <FormField label={t('fields.rateLimit')}>
              <input type="number" {...form.register('rate_limit_per_minute', { valueAsNumber: true })} style={inputStyle} min={1} max={1000} />
            </FormField>
            <FormField label={t('fields.logLevel')}>
              <select {...form.register('log_level')} style={selectStyle}>
                <option value="DEBUG">DEBUG</option>
                <option value="INFO">INFO</option>
                <option value="WARNING">WARNING</option>
                <option value="ERROR">ERROR</option>
              </select>
            </FormField>
            <FormField label={t('fields.enableTelemetry')}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                <input type="checkbox" {...form.register('enable_telemetry')} style={{ width: 16, height: 16 }} />
                <span style={{ fontSize: 13, color: '#6b7280' }}>{t('fields.telemetryHint')}</span>
              </label>
            </FormField>
          </SettingsCard>

          {/* 沙箱设置 */}
          <SettingsCard title={t('sections.sandbox')} icon={<ICONS.documents size={18} />}>
            <FormField label={t('fields.sandboxMode')}>
              <select {...form.register('sandbox_mode')} style={selectStyle}>
                <option value="lightweight">{t('fields.sandboxModeLightweight')}</option>
                <option value="docker">{t('fields.sandboxModeDocker')}</option>
              </select>
            </FormField>
            <FormField label={t('fields.maxFileUpload')}>
              <input type="number" {...form.register('max_file_upload_mb', { valueAsNumber: true })} style={inputStyle} min={1} max={500} />
            </FormField>
          </SettingsCard>

        </div>
      </form>

      {/* 健康检查卡片 */}
      <div style={{ marginTop: 24, background: '#fff', borderRadius: 12, border: '1px solid #e5e7eb', padding: 20 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h2 style={{ fontSize: 18, fontWeight: 600, margin: 0 }}>{t('health.title')}</h2>
          <button onClick={() => refetchHealth()} disabled={healthFetching} style={btnSmallStyle}>
            <ICONS.refresh size={14} /> {healthFetching ? t('health.checking') : t('health.refresh')}
          </button>
        </div>

        {healthError && (
          <div style={{ padding: 12, background: '#fef2f2', borderRadius: 8, marginBottom: 12, color: '#991b1b', fontSize: 13, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
            <span>{getErrorMessage(healthError, t('errors.healthFailed'))}</span>
            <button onClick={() => refetchHealth()} disabled={healthFetching} style={btnSmallStyle}>
              <ICONS.refresh size={14} /> {t('health.retry')}
            </button>
          </div>
        )}

        {healthLoading && !health && (
          <Loading text={t('health.checking')} />
        )}

        {health && (
          <div>
            <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
              <span style={{
                ...(health.status === 'healthy' || health.status === 'ok'
                  ? { background: '#dcfce7', color: '#166534' }
                  : { background: '#fef3c7', color: '#92400e' }),
                padding: '2px 12px', borderRadius: 20, fontSize: 13, fontWeight: 500,
              }}>
                {t('health.overall', { status: formatHealthStatus(health.status, t) })}
              </span>
            </div>

            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #e5e7eb' }}>
                  <th style={thStyle}>{t('health.columns.component')}</th>
                  <th style={thStyle}>{t('health.columns.status')}</th>
                  <th style={thStyle}>{t('health.columns.latency')}</th>
                  <th style={thStyle}>{t('health.columns.detail')}</th>
                </tr>
              </thead>
              <tbody>
                <HealthRow name={t('health.components.database')} item={health.database} />
                <HealthRow name={t('health.components.vectorStore')} item={{ status: health.vector_store?.status ?? 'unavailable', latency_ms: 0 }} extra={health.vector_store?.message} />
                <HealthRow name={t('health.components.llm')} item={{ status: health.default_llm?.status ?? 'unknown', latency_ms: 0 }} extra={health.default_llm?.model_name} />
                <HealthRow name={t('health.components.sandbox')} item={health.sandbox} />
                <HealthRow
                  name={t('health.components.searchEngine')}
                  item={{
                    status: health.search_engines?.active ? 'available' : 'unconfigured',
                    latency_ms: 0,
                  }}
                  extra={t('health.searchEnginesSummary', { active: health.search_engines?.active ?? 0, total: health.search_engines?.total ?? 0 })}
                />
              </tbody>
            </table>
            {health.timestamp && (
              <div style={{ fontSize: 12, color: '#9ca3af', marginTop: 12 }}>
                {t('health.checkedAt')}: {formatDateTime(health.timestamp)}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function SettingsCard({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #e5e7eb', padding: 20 }}>
      <h3 style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 16, fontWeight: 600, margin: '0 0 16px', color: '#111827' }}>
        {icon}
        {title}
      </h3>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {children}
      </div>
    </div>
  )
}

function FormField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label style={{ display: 'block', fontSize: 13, fontWeight: 500, color: '#374151', marginBottom: 4 }}>
        {label}
      </label>
      {children}
    </div>
  )
}

function HealthRow({ name, item, extra }: { name: string; item: { status?: string; latency_ms?: number }; extra?: string }) {
  const { t } = useTranslation('adminSettings')
  const status = item?.status ?? '—'
  const color =
    status === 'connected' || status === 'available' || status === 'ready' || status === 'healthy'
      ? '#22c55e'
      : status === 'degraded' || status === 'unconfigured'
        ? '#f59e0b'
        : '#ef4444'
  const statusLabel = status === '—' ? '—' : formatHealthStatus(status, t)
  return (
    <tr style={{ borderBottom: '1px solid #f3f4f6' }}>
      <td style={{ padding: '10px 12px', fontWeight: 500 }}>{name}</td>
      <td style={{ padding: '10px 12px' }}>
        <span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: '50%', backgroundColor: color, marginRight: 6 }} />
        {statusLabel}
      </td>
      <td style={{ padding: '10px 12px', color: '#6b7280' }}>
        {item?.latency_ms ? `${item.latency_ms}ms` : '—'}
      </td>
      <td style={{ padding: '10px 12px', color: '#6b7280', fontSize: 13 }}>
        {extra || '—'}
      </td>
    </tr>
  )
}

// Styles
const inputStyle: React.CSSProperties = {
  width: '100%', padding: '8px 12px', border: '1px solid #d1d5db',
  borderRadius: 6, fontSize: 14, boxSizing: 'border-box',
}

const selectStyle: React.CSSProperties = {
  width: '100%', padding: '8px 12px', border: '1px solid #d1d5db',
  borderRadius: 6, fontSize: 14, background: '#fff', boxSizing: 'border-box',
}

const thStyle: React.CSSProperties = {
  padding: '8px 12px', textAlign: 'left', fontSize: 13, color: '#6b7280', fontWeight: 600,
}

const btnPrimaryStyle: React.CSSProperties = {
  padding: '8px 16px', border: 'none', borderRadius: 6,
  background: '#3b82f6', color: '#fff', cursor: 'pointer',
  fontSize: 14, fontWeight: 500,
}

const btnSecondaryStyle: React.CSSProperties = {
  padding: '8px 16px', border: '1px solid #d1d5db', borderRadius: 6,
  background: '#fff', color: '#374151', cursor: 'pointer', fontSize: 14,
}

const btnSmallStyle: React.CSSProperties = {
  padding: '4px 8px', border: '1px solid #d1d5db', borderRadius: 6,
  background: '#fff', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 4,
  fontSize: 13,
}
