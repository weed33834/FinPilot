import { useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
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

/** 顶部筛选 Tab 与展示文案。value 与后端 config_type 对应。 */
const CONFIG_TYPE_TABS: { value: string; label: string }[] = [
  { value: 'sql_whitelist', label: 'SQL 白名单' },
  { value: 'code_sandbox', label: '代码沙箱' },
  { value: 'file_upload', label: '文件上传' },
]

const TYPE_LABELS: Record<string, string> = Object.fromEntries(
  CONFIG_TYPE_TABS.map((t) => [t.value, t.label]),
)

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
  const { t } = useTranslation('common')
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
  const { data: configsResp, isLoading, isError, error } = useQuery({
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

  // 选择器选项：优先使用后端返回的类型，未加载时回退到固定 Tab。
  const typeOptions = useMemo<{ value: string; label: string; description: string }[]>(
    () =>
      configTypes.length > 0
        ? configTypes.map((c) => ({
            value: c.value,
            label: c.label,
            description: c.description,
          }))
        : CONFIG_TYPE_TABS.map((t) => ({
            value: t.value,
            label: t.label,
            description: '',
          })),
    [configTypes],
  )

  const defaultConfigForType = (type: string): Record<string, unknown> =>
    configTypes.find((c) => c.value === type)?.default_config ?? {}

  const typeLabel = (value: string): string =>
    TYPE_LABELS[value] ||
    configTypes.find((c) => c.value === value)?.label ||
    value

  // ---- Mutations ----
  const invalidateAll = () =>
    queryClient.invalidateQueries({ queryKey: SANDBOX_QUERY_KEY })

  const createMut = useMutation({
    mutationFn: (payload: SandboxConfigCreatePayload) => createSandboxConfig(payload),
    onSuccess: () => {
      toast.success(t('sandboxConfig.createSuccess', '配置创建成功'))
      invalidateAll()
      setFormOpen(false)
    },
    onError: (err: unknown) =>
      toast.error(t('status.failed', '操作失败'), getErrorMessage(err, '创建失败')),
  })

  const updateMut = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: SandboxConfigUpdatePayload }) =>
      updateSandboxConfig(id, payload),
    onSuccess: () => {
      toast.success(t('sandboxConfig.updateSuccess', '配置已更新'))
      invalidateAll()
      setFormOpen(false)
    },
    onError: (err: unknown) =>
      toast.error(t('status.failed', '操作失败'), getErrorMessage(err, '更新失败')),
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteSandboxConfig(id),
    onSuccess: () => {
      toast.success(t('sandboxConfig.deleteSuccess', '配置已删除'))
      invalidateAll()
    },
    onError: (err: unknown) =>
      toast.error(t('status.failed', '操作失败'), getErrorMessage(err, '删除失败')),
  })

  const toggleMut = useMutation({
    mutationFn: (id: string) => toggleSandboxConfig(id),
    onSuccess: () => {
      toast.success(t('status.success', '操作成功'))
      invalidateAll()
    },
    onError: (err: unknown) =>
      toast.error(t('status.failed', '操作失败'), getErrorMessage(err, '操作失败')),
  })

  // Phase 7：实例生命周期
  const instanceMut = useMutation({
    mutationFn: async ({ action, id }: { action: 'start' | 'stop' | 'restart'; id: string }) => {
      if (action === 'start') return startSandboxInstance(id)
      if (action === 'stop') return stopSandboxInstance(id)
      return restartSandboxInstance(id)
    },
    onSuccess: (_data, vars) => {
      const labels = { start: '已启动', stop: '已停止', restart: '已重启' }
      toast.success(`沙箱实例${labels[vars.action]}`)
      queryClient.invalidateQueries({ queryKey: [...SANDBOX_QUERY_KEY, 'instances'] })
    },
    onError: (err: unknown) =>
      toast.error(t('status.failed', '操作失败'), getErrorMessage(err, '实例操作失败')),
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
      toast.error(t('sandboxConfig.invalidJson', '配置 JSON 格式错误'))
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
      title: t('sandboxConfig.deleteTitle', '确认删除配置'),
      message: (
        <>
          {t('sandboxConfig.deleteConfirm', '确定要删除配置')}「
          <strong>{item.name}</strong>」？
          <br />
          <span className="text-muted text-sm">
            {t('sandboxConfig.deleteTip', '此操作不可恢复。')}
          </span>
        </>
      ),
      confirmText: t('actions.delete', '删除'),
      cancelText: t('actions.cancel', '取消'),
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
      toast.error('请输入要执行的代码')
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
      toast.success(d.success ? '执行成功' : '执行完成（含错误）')
    } catch (err) {
      toast.error(getErrorMessage(err, '执行失败'))
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
      toast.error(getErrorMessage(err, '加载执行历史失败'))
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
          <h1>{t('sandboxConfig.title', '沙箱配置管理')}</h1>
          <p>{t('sandboxConfig.subtitle', '管理 SQL 白名单、代码沙箱与文件上传等安全策略配置。')}</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => {
              queryClient.invalidateQueries({ queryKey: [...SANDBOX_QUERY_KEY, 'health'] })
            }}
            title="执行 print('ok') 验证沙箱可用性"
          >
            <ICONS.security size={16} /> 健康检查
          </button>
          <button type="button" className="btn btn-primary" onClick={openCreate}>
            <ICONS.templates size={16} /> {t('sandboxConfig.addConfig', '添加配置')}
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
        {CONFIG_TYPE_TABS.map((tab) => (
          <ActiveConfigPreview key={tab.value} configType={tab.value} label={tab.label} />
        ))}
      </div>

      {/* Filter tabs */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
        <FilterTab active={activeType === ''} onClick={() => setActiveType('')}>
          {t('common.all', '全部')}
        </FilterTab>
        {CONFIG_TYPE_TABS.map((tab) => (
          <FilterTab
            key={tab.value}
            active={activeType === tab.value}
            onClick={() => setActiveType(tab.value)}
          >
            {tab.label}
          </FilterTab>
        ))}
      </div>

      {/* Table */}
      {isLoading ? (
        <Loading text={t('status.loading', '加载中...')} />
      ) : isError ? (
        <div className="alert alert-error">
          {getErrorMessage(error, t('sandboxConfig.loadFailed', '加载配置列表失败'))}
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          title={t('sandboxConfig.empty', '暂无沙箱配置')}
          description={t('sandboxConfig.emptyDesc', '点击「添加配置」创建第一条安全策略。')}
        />
      ) : (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>{t('sandboxConfig.name', '名称')}</th>
                <th>{t('sandboxConfig.configType', '配置类型')}</th>
                <th>{t('sandboxConfig.description', '描述')}</th>
                <th>{t('sandboxConfig.status', '状态')}</th>
                <th style={{ textAlign: 'center' }}>{t('sandboxConfig.priority', '优先级')}</th>
                <th style={{ textAlign: 'right' }}>{t('sandboxConfig.actions', '操作')}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td>
                    {item.name}
                    {item.is_system && (
                      <span className="badge" style={{ marginLeft: 8 }}>
                        {t('sandboxConfig.system', '系统')}
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
                        {t('actions.enable', '启用')}
                      </span>
                    ) : (
                      <span className="badge rejected">
                        {t('actions.disable', '禁用')}
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
                            ? t('actions.disable', '禁用')
                            : t('actions.enable', '启用')
                        }
                      >
                        {item.is_active
                          ? t('actions.disable', '禁用')
                          : t('actions.enable', '启用')}
                      </button>
                      <button
                        type="button"
                        className="btn btn-sm btn-secondary"
                        onClick={() => openEdit(item)}
                        title={t('actions.edit', '编辑')}
                      >
                        <ICONS.settings size={14} /> {t('actions.edit', '编辑')}
                      </button>
                      {item.config_type === 'code_sandbox' && (
                        <>
                          <button
                            type="button"
                            className="btn btn-sm btn-success"
                            onClick={() => instanceMut.mutate({ action: 'start', id: item.id })}
                            disabled={instanceMut.isPending}
                            title="标记沙箱实例为运行中"
                          >
                            启动
                          </button>
                          <button
                            type="button"
                            className="btn btn-sm btn-secondary"
                            onClick={() => instanceMut.mutate({ action: 'stop', id: item.id })}
                            disabled={instanceMut.isPending}
                            title="停止沙箱实例"
                          >
                            停止
                          </button>
                          <button
                            type="button"
                            className="btn btn-sm btn-secondary"
                            onClick={() => instanceMut.mutate({ action: 'restart', id: item.id })}
                            disabled={instanceMut.isPending}
                            title="重启沙箱实例"
                          >
                            重启
                          </button>
                          <button
                            type="button"
                            className="btn btn-sm btn-primary"
                            onClick={() => openExec(item)}
                            title="在该沙箱配置下执行一段 Python 代码并持久化结果"
                          >
                            <ICONS.send size={14} /> 测试执行
                          </button>
                          <button
                            type="button"
                            className="btn btn-sm btn-secondary"
                            onClick={() => openHistory(item)}
                            title="查看历史执行记录"
                          >
                            <ICONS.reports size={14} /> 历史
                          </button>
                        </>
                      )}
                      {!item.is_system && (
                        <button
                          type="button"
                          className="btn btn-sm btn-danger"
                          onClick={() => handleDelete(item)}
                          disabled={deleteMut.isPending}
                          title={t('actions.delete', '删除')}
                        >
                          <ICONS.close size={14} /> {t('actions.delete', '删除')}
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
              ? t('sandboxConfig.editTitle', '编辑配置')
              : t('sandboxConfig.createTitle', '新建配置')
          }
          onClose={() => setFormOpen(false)}
          footer={
            <>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setFormOpen(false)}
              >
                {t('actions.cancel', '取消')}
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleSubmit}
                disabled={submitting}
              >
                {submitting ? t('status.saving', '保存中...') : t('actions.save', '保存')}
              </button>
            </>
          }
        >
          <div className="form-group">
            <label>{t('sandboxConfig.configType', '配置类型')}</label>
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
            <label>{t('sandboxConfig.name', '名称')}</label>
            <input
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              placeholder={t('sandboxConfig.namePlaceholder', '如 生产环境 SQL 白名单')}
            />
          </div>

          <div className="form-group">
            <label>{t('sandboxConfig.description', '描述')}</label>
            <input
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
              placeholder={t('sandboxConfig.descriptionPlaceholder', '配置用途说明')}
            />
          </div>

          <div className="form-group">
            <label>{t('sandboxConfig.config', '配置 (JSON)')}</label>
            <textarea
              rows={10}
              value={form.configText}
              onChange={(e) => setForm((f) => ({ ...f, configText: e.target.value }))}
              placeholder="{}"
              style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8125rem' }}
            />
            <span className="text-muted text-sm">
              {t('sandboxConfig.configHint', '切换配置类型会按默认模板自动填充。')}
            </span>
          </div>

          <div className="form-group">
            <label>{t('sandboxConfig.priority', '优先级')}</label>
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
              {t('sandboxConfig.isActive', '启用该配置')}
            </label>
          </div>
        </Modal>
      )}

      {/* Phase 7：测试执行 Modal */}
      {execOpen && execTarget && (
        <Modal
          title={`测试执行 — ${execTarget.name}`}
          onClose={() => setExecOpen(false)}
          footer={
            <>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setExecOpen(false)}
              >
                关闭
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleExec}
                disabled={execBusy || !execCode.trim()}
              >
                {execBusy ? '执行中...' : '执行代码'}
              </button>
            </>
          }
        >
          <div style={{ marginBottom: 12 }}>
            <label style={{ display: 'block', marginBottom: 6, fontWeight: 600 }}>
              Python 代码
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
              支持白名单内的模块（math/json/datetime/numpy/pandas 等）。结果会持久化到执行历史。
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
                  状态：
                  <strong style={{ color: execResult.success ? 'var(--color-success)' : 'var(--color-danger)' }}>
                    {execResult.success ? '成功' : '失败'}
                  </strong>
                </span>
                <span>退出码：{execResult.exit_code}</span>
                <span>耗时：{execResult.duration_ms}ms</span>
              </div>
              {execResult.stdout && (
                <div style={{ marginBottom: 8 }}>
                  <strong style={{ fontSize: 12 }}>stdout：</strong>
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
                  <strong style={{ fontSize: 12 }}>stderr：</strong>
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
          title={`执行历史 — ${historyTarget.name}`}
          onClose={() => setHistoryOpen(false)}
        >
          {historyLoading ? (
            <Loading text="加载历史记录..." />
          ) : historyItems.length === 0 ? (
            <EmptyState title="暂无执行记录" description="点击「测试执行」生成首条记录" />
          ) : (
            <div className="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th style={{ width: 60 }}>ID</th>
                    <th>状态</th>
                    <th>退出码</th>
                    <th>耗时</th>
                    <th>触发来源</th>
                    <th>时间</th>
                    <th>代码摘要</th>
                  </tr>
                </thead>
                <tbody>
                  {historyItems.map((h) => (
                    <tr key={h.id}>
                      <td className="text-sm text-muted">#{h.id}</td>
                      <td>
                        {h.success ? (
                          <span className="badge success">成功</span>
                        ) : (
                          <span className="badge rejected">失败</span>
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
          沙箱健康状态
        </div>
        <button
          type="button"
          className="btn btn-sm btn-secondary"
          onClick={() => refetch()}
          disabled={isFetching}
          title="重新执行健康检查"
        >
          {isFetching ? '检查中...' : '刷新'}
        </button>
      </div>
      {isLoading ? (
        <span className="text-sm text-muted">正在执行 print('ok') 验证沙箱可用性...</span>
      ) : isError ? (
        <span className="text-sm" style={{ color: 'var(--color-danger)' }}>
          健康检查失败：{getErrorMessage(error, '未知错误')}
        </span>
      ) : info ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 12 }}>
          <div>
            <div className="text-sm text-muted">状态</div>
            <div
              className="badge"
              style={{
                background: healthy ? 'var(--color-success)' : 'var(--color-danger)',
                color: '#fff',
              }}
            >
              {healthy ? '健康' : '异常'}
            </div>
          </div>
          <div>
            <div className="text-sm text-muted">执行模式</div>
            <div className="text-sm" style={{ fontFamily: 'var(--font-mono)' }}>
              {info.mode || '—'}
            </div>
          </div>
          <div>
            <div className="text-sm text-muted">Docker 镜像</div>
            <div className="text-sm" style={{ fontFamily: 'var(--font-mono)' }}>
              {info.docker_image || '—'}
            </div>
          </div>
          <div>
            <div className="text-sm text-muted">Docker 可用</div>
            <div className="text-sm">{info.docker_available ? '是' : '否'}</div>
          </div>
          <div>
            <div className="text-sm text-muted">延迟</div>
            <div className="text-sm">{info.latency_ms ?? '—'} ms</div>
          </div>
          <div>
            <div className="text-sm text-muted">检查时间</div>
            <div className="text-sm text-muted">{info.checked_at}</div>
          </div>
          {info.error && (
            <div style={{ gridColumn: '1 / -1' }}>
              <div className="text-sm text-muted">错误信息</div>
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
  const { t } = useTranslation('common')
  const { data, isLoading, isError } = useQuery({
    queryKey: [...SANDBOX_QUERY_KEY, 'active', configType],
    queryFn: () => getActiveConfig(configType).then((r) => r.data.data),
    staleTime: 30_000,
  })

  return (
    <div className="card">
      <div className="card-title">{label}</div>
      {isLoading ? (
        <span className="text-sm text-muted">{t('status.loading', '加载中...')}</span>
      ) : isError || !data ? (
        <span className="text-sm text-muted">
          {t('sandboxConfig.noActive', '暂无激活配置')}
        </span>
      ) : (
        <>
          <div className="text-sm text-muted" style={{ marginBottom: 6 }}>
            {t('sandboxConfig.source', '来源')}：{data.name || data.source}
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
