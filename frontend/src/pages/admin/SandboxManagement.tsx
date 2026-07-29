import { useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Trans, useTranslation } from 'react-i18next'
import Modal from '../../components/ui/Modal.tsx'
import Loading from '../../components/ui/Loading.tsx'
import EmptyState from '../../components/ui/EmptyState.tsx'
import { ICONS } from '../../components/ui/Icons.tsx'
import { toast } from '../../components/ui/Toaster.tsx'
import { confirm } from '../../components/ui/ConfirmDialog.tsx'
import { getErrorMessage } from '../../utils/errors.ts'
import {
  listSandboxConfigs,
  listConfigTypes,
  createSandboxConfig,
  updateSandboxConfig,
  deleteSandboxConfig,
  toggleSandboxConfig,
  getActiveConfig,
  getSandboxHealth,
  startSandboxInstance,
  stopSandboxInstance,
  restartSandboxInstance,
  testExecuteSandbox,
  listSandboxExecutions,
  type SandboxConfigItem,
  type SandboxConfigCreatePayload,
  type SandboxConfigUpdatePayload,
  type ConfigTypeItem,
  type SandboxExecutionItem,
  type SandboxHealthInfo,
} from '../../api/sandboxConfigs.ts'

// --------------- Constants ---------------

/** 顶部筛选 Tab 的 config_type 取值（label 走 i18n）。value 与后端 config_type 对应。 */
const CONFIG_TYPE_VALUES = ['sql_whitelist', 'code_sandbox', 'file_upload'] as const

// 命令式确认弹窗默认输入类型，与 ConfirmOptions 一致。
const SANDBOX_QUERY_KEY = ['sandbox-configs'] as const

// --------------- Form ---------------

interface SandboxFormState {
  config_type: string
  name: string
  description: string
  /** config 字段的原始 JSON 文本，便于在 textarea 中编辑。 */
  configText: string
  priority: number
  is_active: boolean
}

const EMPTY_FORM: SandboxFormState = {
  config_type: 'sql_whitelist',
  name: '',
  description: '',
  configText: '{}',
  priority: 0,
  is_active: true,
}

function safeStringify(value: unknown): string {
  try {
    return JSON.stringify(value ?? {}, null, 2)
  } catch {
    return '{}'
  }
}

// --------------- Component ---------------

export default function SandboxManagement() {
  const { t } = useTranslation('adminSandbox')
  const queryClient = useQueryClient()

  const [activeType, setActiveType] = useState('')
  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<SandboxConfigItem | null>(null)
  const [form, setForm] = useState<SandboxFormState>(EMPTY_FORM)

  // Phase 7：测试执行 + 历史记录 + 健康检查 + 实例生命周期
  const [execOpen, setExecOpen] = useState(false)
  const [execTarget, setExecTarget] = useState<SandboxConfigItem | null>(null)
  const [execCode, setExecCode] = useState("print('Hello from FinPilot sandbox')\nimport math\nprint(f'pi={math.pi:.4f}')")
  const [execResult, setExecResult] = useState<{
    success: boolean
    stdout: string
    stderr: string
    exit_code: number
    duration_ms: number
  } | null>(null)
  const [execBusy, setExecBusy] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [historyTarget, setHistoryTarget] = useState<SandboxConfigItem | null>(null)
  const [historyItems, setHistoryItems] = useState<SandboxExecutionItem[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)

  // ---- Queries ----
  const { data: configsResp, isLoading, isError, error, refetch } = useQuery({
    queryKey: [...SANDBOX_QUERY_KEY, 'list', activeType],
    queryFn: () =>
      listSandboxConfigs(activeType ? { config_type: activeType } : undefined),
  })
  const items: SandboxConfigItem[] = configsResp?.data?.data ?? []

  const { data: typesResp } = useQuery({
    queryKey: [...SANDBOX_QUERY_KEY, 'types'],
    queryFn: () => listConfigTypes(),
  })
  const configTypes: ConfigTypeItem[] = typesResp?.data?.data ?? []

  // 选择器选项：优先使用后端返回的类型，未加载时回退到固定取值。label 走 i18n。
  const typeOptions = useMemo<{ value: string; label: string; description: string }[]>(
    () =>
      configTypes.length > 0
        ? configTypes.map((c) => ({
            value: c.value,
            label: t(`configTypes.${c.value}`, { defaultValue: c.label }),
            description: c.description,
          }))
        : CONFIG_TYPE_VALUES.map((v) => ({
            value: v,
            label: t(`configTypes.${v}`),
            description: '',
          })),
    [configTypes, t],
  )

  const defaultConfigForType = (type: string): Record<string, unknown> =>
    configTypes.find((c) => c.value === type)?.default_config ?? {}

  const typeLabel = (value: string): string => {
    const fromBackend = configTypes.find((c) => c.value === value)?.label
    return t(`configTypes.${value}`, { defaultValue: fromBackend || value })
  }

  // ---- Mutations ----
  const invalidateAll = () =>
    queryClient.invalidateQueries({ queryKey: SANDBOX_QUERY_KEY })

  const createMut = useMutation({
    mutationFn: (payload: SandboxConfigCreatePayload) => createSandboxConfig(payload),
    onSuccess: () => {
      toast.success(t('toast.createSuccess'))
      invalidateAll()
      setFormOpen(false)
    },
    onError: (err: unknown) =>
      toast.error(t('toast.operationFailed'), getErrorMessage(err, t('toast.createFailed'))),
  })

  const updateMut = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: SandboxConfigUpdatePayload }) =>
      updateSandboxConfig(id, payload),
    onSuccess: () => {
      toast.success(t('toast.updateSuccess'))
      invalidateAll()
      setFormOpen(false)
    },
    onError: (err: unknown) =>
      toast.error(t('toast.operationFailed'), getErrorMessage(err, t('toast.updateFailed'))),
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteSandboxConfig(id),
    onSuccess: () => {
      toast.success(t('toast.deleteSuccess'))
      invalidateAll()
    },
    onError: (err: unknown) =>
      toast.error(t('toast.operationFailed'), getErrorMessage(err, t('toast.deleteFailed'))),
  })

  const toggleMut = useMutation({
    mutationFn: (id: string) => toggleSandboxConfig(id),
    onSuccess: () => {
      toast.success(t('toast.toggleSuccess'))
      invalidateAll()
    },
    onError: (err: unknown) =>
      toast.error(t('toast.operationFailed'), getErrorMessage(err, t('toast.toggleFailed'))),
  })

  // Phase 7：实例生命周期
  const instanceMut = useMutation({
    mutationFn: async ({ action, id }: { action: 'start' | 'stop' | 'restart'; id: string }) => {
      if (action === 'start') return startSandboxInstance(id)
      if (action === 'stop') return stopSandboxInstance(id)
      return restartSandboxInstance(id)
    },
    onSuccess: (_data, vars) => {
      const keyMap = {
        start: 'toast.instanceStarted',
        stop: 'toast.instanceStopped',
        restart: 'toast.instanceRestarted',
      } as const
      toast.success(t(keyMap[vars.action]))
      queryClient.invalidateQueries({ queryKey: [...SANDBOX_QUERY_KEY, 'instances'] })
    },
    onError: (err: unknown) =>
      toast.error(t('toast.operationFailed'), getErrorMessage(err, t('toast.instanceFailed'))),
  })

  // ---- Handlers ----
  const openCreate = () => {
    const firstType = typeOptions[0]?.value ?? 'sql_whitelist'
    setEditing(null)
    setForm({
      config_type: firstType,
      name: '',
      description: '',
      configText: safeStringify(defaultConfigForType(firstType)),
      priority: 0,
      is_active: true,
    })
    setFormOpen(true)
  }

  const openEdit = (item: SandboxConfigItem) => {
    setEditing(item)
    setForm({
      config_type: item.config_type,
      name: item.name,
      description: item.description ?? '',
      configText: safeStringify(item.config ?? {}),
      priority: item.priority,
      is_active: item.is_active,
    })
    setFormOpen(true)
  }

  // 创建态切换 config_type 时，按后端 default_config 预填 config。
  const handleTypeChange = (newType: string) => {
    setForm((f) => ({
      ...f,
      config_type: newType,
      configText: safeStringify(defaultConfigForType(newType)),
    }))
  }

  const handleSubmit = () => {
    let parsedConfig: Record<string, unknown>
    try {
      const trimmed = form.configText.trim()
      parsedConfig = trimmed ? JSON.parse(trimmed) : {}
      if (!parsedConfig || typeof parsedConfig !== 'object' || Array.isArray(parsedConfig)) {
        throw new Error('invalid config')
      }
    } catch {
      toast.error(t('form.invalidJson'))
      return
    }

    if (editing) {
      updateMut.mutate({
        id: editing.id,
        payload: {
          name: form.name,
          description: form.description,
          config: parsedConfig,
          is_active: form.is_active,
          priority: form.priority,
        },
      })
    } else {
      createMut.mutate({
        config_type: form.config_type,
        name: form.name,
        description: form.description,
        config: parsedConfig,
        is_active: form.is_active,
        priority: form.priority,
      })
    }
  }

  const handleDelete = async (item: SandboxConfigItem) => {
    const ok = await confirm({
      title: t('confirm.deleteTitle'),
      message: (
        <>
          <Trans
            i18nKey="confirm.deleteConfirm"
            ns="adminSandbox"
            values={{ name: item.name }}
            components={{ strong: <strong /> }}
          />
          <br />
          <span className="text-muted text-sm">
            {t('confirm.deleteTip')}
          </span>
        </>
      ),
      confirmText: t('confirm.delete'),
      cancelText: t('confirm.cancel'),
      variant: 'danger',
    })
    if (ok) deleteMut.mutate(item.id)
  }

  // ---- Phase 7：测试执行 + 历史记录 ----
  const openExec = (item: SandboxConfigItem) => {
    setExecTarget(item)
    setExecResult(null)
    setExecOpen(true)
  }

  const handleExec = async () => {
    if (!execTarget) return
    if (!execCode.trim()) {
      toast.error(t('exec.codeRequired'))
      return
    }
    setExecBusy(true)
    setExecResult(null)
    try {
      const res = await testExecuteSandbox(execTarget.id, { code: execCode, timeout: 30 })
      const d = res.data.data
      setExecResult({
        success: d.success,
        stdout: d.stdout,
        stderr: d.stderr,
        exit_code: d.exit_code,
        duration_ms: d.duration_ms,
      })
      toast.success(d.success ? t('exec.execSuccess') : t('exec.execCompletedWithErrors'))
    } catch (err) {
      toast.error(getErrorMessage(err, t('exec.execFailed')))
    } finally {
      setExecBusy(false)
    }
  }

  const openHistory = async (item: SandboxConfigItem) => {
    setHistoryTarget(item)
    setHistoryOpen(true)
    setHistoryLoading(true)
    setHistoryItems([])
    try {
      const res = await listSandboxExecutions(item.id, { page: 1, page_size: 50 })
      setHistoryItems(res.data.data.items)
    } catch (err) {
      toast.error(getErrorMessage(err, t('history.loadFailed')))
    } finally {
      setHistoryLoading(false)
    }
  }

  const submitting = createMut.isPending || updateMut.isPending

  return (
    <div className="container">
      {/* Header */}
      <div className="page-header">
        <div>
          <h1>{t('title')}</h1>
          <p>{t('subtitle')}</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => {
              queryClient.invalidateQueries({ queryKey: [...SANDBOX_QUERY_KEY, 'health'] })
            }}
            title={t('actions.healthCheckTitle')}
          >
            <ICONS.security size={16} /> {t('actions.healthCheck')}
          </button>
          <button type="button" className="btn btn-primary" onClick={openCreate}>
            <ICONS.templates size={16} /> {t('actions.addConfig')}
          </button>
        </div>
      </div>

      {/* Phase 7：沙箱健康检查卡片 */}
      <HealthCheckCard />

      {/* Active config preview per type */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
          gap: 12,
          marginBottom: 16,
        }}
      >
        {CONFIG_TYPE_VALUES.map((value) => (
          <ActiveConfigPreview
            key={value}
            configType={value}
            label={t(`configTypes.${value}`)}
          />
        ))}
      </div>

      {/* Filter tabs */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
        <FilterTab active={activeType === ''} onClick={() => setActiveType('')}>
          {t('filters.all')}
        </FilterTab>
        {CONFIG_TYPE_VALUES.map((value) => (
          <FilterTab
            key={value}
            active={activeType === value}
            onClick={() => setActiveType(value)}
          >
            {t(`configTypes.${value}`)}
          </FilterTab>
        ))}
      </div>

      {/* Table */}
      {isLoading ? (
        <Loading text={t('status.loading')} />
      ) : isError ? (
        <div className="alert alert-error">
          <div>{getErrorMessage(error, t('errors.loadFailed'))}</div>
          <button
            type="button"
            className="btn btn-sm btn-secondary"
            onClick={() => refetch()}
            style={{ marginTop: 8 }}
          >
            <ICONS.refresh size={14} /> {t('errors.retry')}
          </button>
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          title={t('empty.title')}
          description={t('empty.description')}
        />
      ) : (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>{t('table.name')}</th>
                <th>{t('table.configType')}</th>
                <th>{t('table.description')}</th>
                <th>{t('table.status')}</th>
                <th style={{ textAlign: 'center' }}>{t('table.priority')}</th>
                <th style={{ textAlign: 'right' }}>{t('table.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td>
                    {item.name}
                    {item.is_system && (
                      <span className="badge" style={{ marginLeft: 8 }}>
                        {t('badge.system')}
                      </span>
                    )}
                  </td>
                  <td>
                    <span className="badge">{typeLabel(item.config_type)}</span>
                  </td>
                  <td className="text-sm text-muted">{item.description || '—'}</td>
                  <td>
                    {item.is_active ? (
                      <span className="badge success">
                        {t('status.enabled')}
                      </span>
                    ) : (
                      <span className="badge rejected">
                        {t('status.disabled')}
                      </span>
                    )}
                  </td>
                  <td style={{ textAlign: 'center' }}>{item.priority}</td>
                  <td style={{ textAlign: 'right' }}>
                    <div className="action-group" style={{ justifyContent: 'flex-end', flexWrap: 'wrap', gap: 4 }}>
                      <button
                        type="button"
                        className="btn btn-sm btn-secondary"
                        onClick={() => toggleMut.mutate(item.id)}
                        disabled={toggleMut.isPending}
                        title={
                          item.is_active
                            ? t('actions.disable')
                            : t('actions.enable')
                        }
                      >
                        {item.is_active
                          ? t('actions.disable')
                          : t('actions.enable')}
                      </button>
                      <button
                        type="button"
                        className="btn btn-sm btn-secondary"
                        onClick={() => openEdit(item)}
                        title={t('actions.edit')}
                      >
                        <ICONS.settings size={14} /> {t('actions.edit')}
                      </button>
                      {item.config_type === 'code_sandbox' && (
                        <>
                          <button
                            type="button"
                            className="btn btn-sm btn-success"
                            onClick={() => instanceMut.mutate({ action: 'start', id: item.id })}
                            disabled={instanceMut.isPending}
                            title={t('actions.startTitle')}
                          >
                            {t('actions.start')}
                          </button>
                          <button
                            type="button"
                            className="btn btn-sm btn-secondary"
                            onClick={() => instanceMut.mutate({ action: 'stop', id: item.id })}
                            disabled={instanceMut.isPending}
                            title={t('actions.stopTitle')}
                          >
                            {t('actions.stop')}
                          </button>
                          <button
                            type="button"
                            className="btn btn-sm btn-secondary"
                            onClick={() => instanceMut.mutate({ action: 'restart', id: item.id })}
                            disabled={instanceMut.isPending}
                            title={t('actions.restartTitle')}
                          >
                            {t('actions.restart')}
                          </button>
                          <button
                            type="button"
                            className="btn btn-sm btn-primary"
                            onClick={() => openExec(item)}
                            title={t('actions.testExecTitle')}
                          >
                            <ICONS.send size={14} /> {t('actions.testExec')}
                          </button>
                          <button
                            type="button"
                            className="btn btn-sm btn-secondary"
                            onClick={() => openHistory(item)}
                            title={t('actions.historyTitle')}
                          >
                            <ICONS.reports size={14} /> {t('actions.history')}
                          </button>
                        </>
                      )}
                      {!item.is_system && (
                        <button
                          type="button"
                          className="btn btn-sm btn-danger"
                          onClick={() => handleDelete(item)}
                          disabled={deleteMut.isPending}
                          title={t('actions.delete')}
                        >
                          <ICONS.close size={14} /> {t('actions.delete')}
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Create / Edit Modal */}
      {formOpen && (
        <Modal
          title={
            editing
              ? t('form.editTitle')
              : t('form.createTitle')
          }
          onClose={() => setFormOpen(false)}
          footer={
            <>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setFormOpen(false)}
              >
                {t('actions.cancel')}
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleSubmit}
                disabled={submitting}
              >
                {submitting ? t('status.saving') : t('actions.save')}
              </button>
            </>
          }
        >
          <div className="form-group">
            <label>{t('form.configType')}</label>
            <select
              value={form.config_type}
              onChange={(e) => handleTypeChange(e.target.value)}
              disabled={!!editing}
            >
              {typeOptions.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                  {o.description ? ` — ${o.description}` : ''}
                </option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label>{t('form.name')}</label>
            <input
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              placeholder={t('form.namePlaceholder')}
            />
          </div>

          <div className="form-group">
            <label>{t('form.description')}</label>
            <input
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
              placeholder={t('form.descriptionPlaceholder')}
            />
          </div>

          <div className="form-group">
            <label>{t('form.config')}</label>
            <textarea
              rows={10}
              value={form.configText}
              onChange={(e) => setForm((f) => ({ ...f, configText: e.target.value }))}
              placeholder="{}"
              style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8125rem' }}
            />
            <span className="text-muted text-sm">
              {t('form.configHint')}
            </span>
          </div>

          <div className="form-group">
            <label>{t('form.priority')}</label>
            <input
              type="number"
              value={form.priority}
              onChange={(e) =>
                setForm((f) => ({ ...f, priority: Number(e.target.value) || 0 }))
              }
            />
          </div>

          <div className="form-group">
            <label>
              <input
                type="checkbox"
                checked={form.is_active}
                onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))}
              />{' '}
              {t('form.isActive')}
            </label>
          </div>
        </Modal>
      )}

      {/* Phase 7：测试执行 Modal */}
      {execOpen && execTarget && (
        <Modal
          title={t('exec.title', { name: execTarget.name })}
          onClose={() => setExecOpen(false)}
          footer={
            <>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setExecOpen(false)}
              >
                {t('actions.close')}
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleExec}
                disabled={execBusy || !execCode.trim()}
              >
                {execBusy ? t('exec.executing') : t('exec.runCode')}
              </button>
            </>
          }
        >
          <div style={{ marginBottom: 12 }}>
            <label style={{ display: 'block', marginBottom: 6, fontWeight: 600 }}>
              {t('exec.codeLabel')}
            </label>
            <textarea
              rows={8}
              value={execCode}
              onChange={(e) => setExecCode(e.target.value)}
              style={{
                width: '100%',
                fontFamily: 'var(--font-mono)',
                fontSize: 13,
                padding: 8,
                background: 'var(--color-bg)',
                color: 'var(--color-text)',
                border: '1px solid var(--color-border)',
                borderRadius: 4,
              }}
              placeholder="print('hello')"
            />
            <span className="text-muted text-sm" style={{ display: 'block', marginTop: 4 }}>
              {t('exec.codeHint')}
            </span>
          </div>

          {execResult && (
            <div
              style={{
                marginTop: 12,
                padding: 12,
                border: '1px solid var(--color-border)',
                borderRadius: 4,
                background: 'var(--color-surface-raised)',
              }}
            >
              <div style={{ marginBottom: 6, display: 'flex', gap: 12, fontSize: 12 }}>
                <span>
                  {t('exec.statusLabel')}
                  <strong style={{ color: execResult.success ? 'var(--color-success)' : 'var(--color-danger)' }}>
                    {execResult.success ? t('exec.success') : t('exec.failed')}
                  </strong>
                </span>
                <span>{t('exec.exitCode', { code: execResult.exit_code })}</span>
                <span>{t('exec.duration', { ms: execResult.duration_ms })}</span>
              </div>
              {execResult.stdout && (
                <div style={{ marginBottom: 8 }}>
                  <strong style={{ fontSize: 12 }}>stdout:</strong>
                  <pre
                    style={{
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                      background: 'var(--color-bg)',
                      padding: 8,
                      borderRadius: 2,
                      margin: '4px 0',
                      maxHeight: 200,
                      overflow: 'auto',
                      fontSize: 12,
                      color: 'var(--color-success)',
                    }}
                  >
                    {execResult.stdout}
                  </pre>
                </div>
              )}
              {execResult.stderr && (
                <div>
                  <strong style={{ fontSize: 12 }}>stderr:</strong>
                  <pre
                    style={{
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                      background: 'var(--color-bg)',
                      padding: 8,
                      borderRadius: 2,
                      margin: '4px 0',
                      maxHeight: 200,
                      overflow: 'auto',
                      fontSize: 12,
                      color: 'var(--color-danger)',
                    }}
                  >
                    {execResult.stderr}
                  </pre>
                </div>
              )}
            </div>
          )}
        </Modal>
      )}

      {/* Phase 7：执行历史 Modal */}
      {historyOpen && historyTarget && (
        <Modal
          title={t('history.title', { name: historyTarget.name })}
          onClose={() => setHistoryOpen(false)}
        >
          {historyLoading ? (
            <Loading text={t('history.loading')} />
          ) : historyItems.length === 0 ? (
            <EmptyState title={t('history.empty')} description={t('history.emptyDesc')} />
          ) : (
            <div className="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th style={{ width: 60 }}>{t('history.colId')}</th>
                    <th>{t('history.colStatus')}</th>
                    <th>{t('history.colExitCode')}</th>
                    <th>{t('history.colDuration')}</th>
                    <th>{t('history.colSource')}</th>
                    <th>{t('history.colTime')}</th>
                    <th>{t('history.colCodeSummary')}</th>
                  </tr>
                </thead>
                <tbody>
                  {historyItems.map((h) => (
                    <tr key={h.id}>
                      <td className="text-sm text-muted">#{h.id}</td>
                      <td>
                        {h.success ? (
                          <span className="badge success">{t('history.success')}</span>
                        ) : (
                          <span className="badge rejected">{t('history.failed')}</span>
                        )}
                      </td>
                      <td className="text-sm">{h.exit_code}</td>
                      <td className="text-sm">{h.duration_ms}ms</td>
                      <td>
                        <span className="badge">{h.trigger_source}</span>
                      </td>
                      <td className="text-sm text-muted">{h.created_at}</td>
                      <td>
                        <code
                          style={{
                            fontSize: 12,
                            display: 'block',
                            maxWidth: 320,
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                          }}
                          title={h.code}
                        >
                          {h.code.split('\n')[0]}
                        </code>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Modal>
      )}
    </div>
  )
}

// --------------- Subcomponents ---------------

/** Phase 7：沙箱健康检查卡片 — 调用 /sandbox-configs/health 实际执行 print('ok')。 */
function HealthCheckCard() {
  const { t } = useTranslation('adminSandbox')
  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: [...SANDBOX_QUERY_KEY, 'health'],
    queryFn: () => getSandboxHealth().then((r) => r.data.data),
    staleTime: 0,
    refetchOnMount: true,
  })

  const info: SandboxHealthInfo | undefined = data
  const healthy = info?.healthy === true

  return (
    <div
      className="card"
      style={{
        marginBottom: 16,
        borderColor: healthy ? 'var(--color-success)' : 'var(--color-border)',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 8,
        }}
      >
        <div className="card-title" style={{ margin: 0 }}>
          {t('health.title')}
        </div>
        <button
          type="button"
          className="btn btn-sm btn-secondary"
          onClick={() => refetch()}
          disabled={isFetching}
          title={t('health.refreshTitle')}
        >
          {isFetching ? t('health.checking') : t('actions.refresh')}
        </button>
      </div>
      {isLoading ? (
        <span className="text-sm text-muted">{t('health.checkingHint')}</span>
      ) : isError ? (
        <span className="text-sm" style={{ color: 'var(--color-danger)' }}>
          {t('health.checkFailed')}{getErrorMessage(error, t('health.unknownError'))}
        </span>
      ) : info ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 12 }}>
          <div>
            <div className="text-sm text-muted">{t('health.status')}</div>
            <div
              className="badge"
              style={{
                background: healthy ? 'var(--color-success)' : 'var(--color-danger)',
                color: '#fff',
              }}
            >
              {healthy ? t('health.healthy') : t('health.unhealthy')}
            </div>
          </div>
          <div>
            <div className="text-sm text-muted">{t('health.mode')}</div>
            <div className="text-sm" style={{ fontFamily: 'var(--font-mono)' }}>
              {info.mode || '—'}
            </div>
          </div>
          <div>
            <div className="text-sm text-muted">{t('health.dockerImage')}</div>
            <div className="text-sm" style={{ fontFamily: 'var(--font-mono)' }}>
              {info.docker_image || '—'}
            </div>
          </div>
          <div>
            <div className="text-sm text-muted">{t('health.dockerAvailable')}</div>
            <div className="text-sm">{t(info.docker_available ? 'common.yes' : 'common.no')}</div>
          </div>
          <div>
            <div className="text-sm text-muted">{t('health.latency')}</div>
            <div className="text-sm">{info.latency_ms ?? '—'} ms</div>
          </div>
          <div>
            <div className="text-sm text-muted">{t('health.checkedAt')}</div>
            <div className="text-sm text-muted">{info.checked_at}</div>
          </div>
          {info.error && (
            <div style={{ gridColumn: '1 / -1' }}>
              <div className="text-sm text-muted">{t('health.errorLabel')}</div>
              <pre
                style={{
                  fontSize: 12,
                  color: 'var(--color-danger)',
                  margin: 0,
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                }}
              >
                {info.error}
              </pre>
            </div>
          )}
        </div>
      ) : null}
    </div>
  )
}

/** 单个配置类型的「当前激活配置」预览卡片。 */
function ActiveConfigPreview({
  configType,
  label,
}: {
  configType: string
  label: string
}) {
  const { t } = useTranslation('adminSandbox')
  const { data, isLoading, isError } = useQuery({
    queryKey: [...SANDBOX_QUERY_KEY, 'active', configType],
    queryFn: () => getActiveConfig(configType).then((r) => r.data.data),
    staleTime: 30_000,
  })

  return (
    <div className="card">
      <div className="card-title">{label}</div>
      {isLoading ? (
        <span className="text-sm text-muted">{t('status.loading')}</span>
      ) : isError || !data ? (
        <span className="text-sm text-muted">
          {t('active.noActive')}
        </span>
      ) : (
        <>
          <div className="text-sm text-muted" style={{ marginBottom: 6 }}>
            {t('active.source')}：{data.name || data.source}
          </div>
          <pre
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 12,
              margin: 0,
              maxHeight: 180,
              overflow: 'auto',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
            }}
          >
            {JSON.stringify(data.config ?? {}, null, 2)}
          </pre>
        </>
      )}
    </div>
  )
}

/** 筛选 Tab 按钮：激活态使用主色，非激活态使用 ghost。 */
function FilterTab({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      className={`btn btn-sm${active ? ' btn-primary' : ' btn-ghost'}`}
      onClick={onClick}
    >
      {children}
    </button>
  )
}
