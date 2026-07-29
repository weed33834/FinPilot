import { useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Trans, useTranslation } from 'react-i18next'
import i18n from '../../i18n/config.ts'
import zhCnResource from '../../i18n/locales/zh-CN/admin-mcp-server.json'
import enResource from '../../i18n/locales/en/admin-mcp-server.json'
import Modal from '../../components/ui/Modal.tsx'
import Loading from '../../components/ui/Loading.tsx'
import EmptyState from '../../components/ui/EmptyState.tsx'
import { confirm } from '../../components/ui/ConfirmDialog.tsx'
import { toast } from '../../components/ui/Toaster.tsx'
import { ICONS } from '../../components/ui/Icons.tsx'
import { getErrorMessage } from '../../utils/errors.ts'
import {
  listMcpServers,
  createMcpServer,
  updateMcpServer,
  deleteMcpServer,
  toggleMcpServer,
  testMcpServer,
  listTransports,
  type McpServerItem,
  type McpServerCreatePayload,
  type McpServerUpdatePayload,
} from '../../api/mcpServers.ts'

// 命名空间未在 i18n/config.ts 中注册（按要求不修改该文件），这里在模块加载时
// 同步注入资源，子组件通过 useTranslation('adminMcpServer') 消费。
const NS = 'adminMcpServer'
if (!i18n.hasResourceBundle('zh-CN', NS)) {
  i18n.addResourceBundle('zh-CN', NS, zhCnResource)
}
if (!i18n.hasResourceBundle('en', NS)) {
  i18n.addResourceBundle('en', NS, enResource)
}

interface TransportOption {
  value: string
  label: string
}

interface FormState {
  name: string
  display_name: string
  description: string
  transport: string
  command: string
  url: string
  api_key: string
  env_vars: string
  priority: number
  is_active: boolean
}

const EMPTY_FORM: FormState = {
  name: '',
  display_name: '',
  description: '',
  transport: 'stdio',
  command: '',
  url: '',
  api_key: '',
  env_vars: '{\n}',
  priority: 0,
  is_active: true,
}

const FALLBACK_TRANSPORTS: TransportOption[] = [
  { value: 'stdio', label: 'stdio' },
  { value: 'sse', label: 'sse' },
  { value: 'streamable_http', label: 'streamable_http' },
]

const TRANSPORT_BADGES: Record<string, string> = {
  stdio: 'badge published',
  sse: 'badge success',
  streamable_http: 'badge approved',
}

const LAST_STATUS_OK = ['connected', 'ok', 'success', 'healthy', 'ready']
const LAST_STATUS_BAD = ['error', 'failed', 'disconnected', 'unreachable', 'timeout', 'offline']

function transportBadgeClass(transport: string): string {
  return TRANSPORT_BADGES[transport] || 'badge draft'
}

function LastStatusBadge({ status }: { status: string | null }) {
  const { t } = useTranslation('adminMcpServer')
  if (!status) return <span className="text-muted">—</span>
  const ok = LAST_STATUS_OK.includes(status)
  const bad = LAST_STATUS_BAD.includes(status)
  const cls = ok ? 'badge success' : bad ? 'badge failed' : 'badge draft'
  return <span className={cls}>{t(`lastStatus.${status}`, { defaultValue: status })}</span>
}

interface McpServerFormProps {
  form: FormState
  updateField: <K extends keyof FormState>(key: K, value: FormState[K]) => void
  transportOptions: TransportOption[]
  editingId: string | null
  submitting: boolean
  onClose: () => void
  onSave: () => void
}

function McpServerForm({
  form,
  updateField,
  transportOptions,
  editingId,
  submitting,
  onClose,
  onSave,
}: McpServerFormProps) {
  const { t } = useTranslation('adminMcpServer')
  const isStdio = form.transport === 'stdio'

  return (
    <Modal
      title={editingId ? t('form.editTitle') : t('form.createTitle')}
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            {t('actions.cancel')}
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={onSave}
            disabled={submitting}
          >
            {submitting
              ? t('status.saving')
              : editingId
                ? t('actions.save')
                : t('actions.create')}
          </button>
        </>
      }
    >
      <div className="admin-form-grid">
        <div className="admin-form-group">
          <label>{t('form.name')}</label>
          <input
            type="text"
            value={form.name}
            onChange={(e) => updateField('name', e.target.value)}
            placeholder={t('form.namePlaceholder')}
            disabled={!!editingId}
          />
        </div>
        <div className="admin-form-group">
          <label>{t('form.displayName')}</label>
          <input
            type="text"
            value={form.display_name}
            onChange={(e) => updateField('display_name', e.target.value)}
            placeholder={t('form.displayNamePlaceholder')}
          />
        </div>

        <div className="admin-form-group full-width">
          <label>{t('form.description')}</label>
          <textarea
            value={form.description}
            onChange={(e) => updateField('description', e.target.value)}
            rows={2}
            placeholder={t('form.descriptionPlaceholder')}
          />
        </div>

        <div className="admin-form-group">
          <label>{t('form.transport')}</label>
          <select
            value={form.transport}
            onChange={(e) => updateField('transport', e.target.value)}
          >
            {transportOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {t(`transports.${opt.value}`, { defaultValue: opt.label || opt.value })}
              </option>
            ))}
          </select>
        </div>
        <div className="admin-form-group">
          <label>{t('form.priority')}</label>
          <input
            type="number"
            value={form.priority}
            onChange={(e) => updateField('priority', Number(e.target.value))}
            min={0}
          />
        </div>

        {isStdio ? (
          <div className="admin-form-group full-width">
            <label>{t('form.command')}</label>
            <input
              type="text"
              value={form.command}
              onChange={(e) => updateField('command', e.target.value)}
              placeholder={t('form.commandPlaceholder')}
            />
          </div>
        ) : (
          <div className="admin-form-group full-width">
            <label>{t('form.url')}</label>
            <input
              type="text"
              value={form.url}
              onChange={(e) => updateField('url', e.target.value)}
              placeholder={t('form.urlPlaceholder')}
            />
          </div>
        )}

        <div className="admin-form-group full-width">
          <label>{t('form.apiKey')}</label>
          <input
            type="password"
            value={form.api_key}
            onChange={(e) => updateField('api_key', e.target.value)}
            placeholder={t('form.apiKeyPlaceholder')}
          />
        </div>

        <div className="admin-form-group full-width">
          <label>{t('form.envVars')}</label>
          <textarea
            value={form.env_vars}
            onChange={(e) => updateField('env_vars', e.target.value)}
            rows={5}
            placeholder={t('form.envVarsPlaceholder')}
          />
        </div>

        <div className="full-width">
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(e) => updateField('is_active', e.target.checked)}
            />
            <span>{t('form.isActive')}</span>
          </label>
        </div>
      </div>
    </Modal>
  )
}

export default function McpServerManagement() {
  const { t } = useTranslation('adminMcpServer')
  const queryClient = useQueryClient()

  const [search, setSearch] = useState('')
  const [formOpen, setFormOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [testingId, setTestingId] = useState<string | null>(null)

  const { data: servers, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['mcp-servers'],
    queryFn: () => listMcpServers().then((r) => r.data.data),
  })

  const { data: transports } = useQuery({
    queryKey: ['mcp-servers', 'transports'],
    queryFn: () => listTransports().then((r) => r.data.data),
  })

  const transportOptions = useMemo<TransportOption[]>(() => {
    const fetched = transports ?? []
    return fetched.length > 0 ? fetched : FALLBACK_TRANSPORTS
  }, [transports])

  const filteredServers = useMemo<McpServerItem[]>(() => {
    const all = servers ?? []
    const q = search.trim().toLowerCase()
    if (!q) return all
    return all.filter(
      (s) =>
        s.name.toLowerCase().includes(q) ||
        s.display_name.toLowerCase().includes(q),
    )
  }, [servers, search])

  const createMut = useMutation({
    mutationFn: (payload: McpServerCreatePayload) => createMcpServer(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mcp-servers'] })
      setFormOpen(false)
      toast.success(t('status.success'), t('toast.created'))
    },
    onError: (err: unknown) => toast.error(t('status.failed'), getErrorMessage(err)),
  })

  const updateMut = useMutation({
    mutationFn: (vars: { id: string; payload: McpServerUpdatePayload }) =>
      updateMcpServer(vars.id, vars.payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mcp-servers'] })
      setFormOpen(false)
      setEditingId(null)
      toast.success(t('status.success'), t('toast.updated'))
    },
    onError: (err: unknown) => toast.error(t('status.failed'), getErrorMessage(err)),
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteMcpServer(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mcp-servers'] })
      toast.success(t('status.success'), t('toast.deleted'))
    },
    onError: (err: unknown) => toast.error(t('status.failed'), getErrorMessage(err)),
  })

  const toggleMut = useMutation({
    mutationFn: (id: string) => toggleMcpServer(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mcp-servers'] })
      toast.success(t('status.success'))
    },
    onError: (err: unknown) => toast.error(t('status.failed'), getErrorMessage(err)),
  })

  const testMut = useMutation({
    mutationFn: (id: string) => testMcpServer(id),
    onMutate: (id) => setTestingId(id),
    onSuccess: (res) => {
      const data = res.data.data
      toast.success(
        t('toast.testSuccess'),
        t('toast.testSuccessDesc', {
          name: data.name,
          transport: data.transport,
          status: data.status,
        }),
      )
    },
    onError: (err: unknown) => toast.error(t('toast.testFailed'), getErrorMessage(err)),
    onSettled: () => setTestingId(null),
  })

  const handleCreate = () => {
    setEditingId(null)
    setForm({ ...EMPTY_FORM, transport: transportOptions[0]?.value ?? 'stdio' })
    setFormOpen(true)
  }

  const handleEdit = (server: McpServerItem) => {
    setEditingId(server.id)
    setForm({
      name: server.name,
      display_name: server.display_name,
      description: server.description ?? '',
      transport: server.transport,
      command: server.command ?? '',
      url: server.url ?? '',
      api_key: '',
      env_vars:
        server.env_vars && Object.keys(server.env_vars).length > 0
          ? JSON.stringify(server.env_vars, null, 2)
          : '{\n}',
      priority: server.priority ?? 0,
      is_active: server.is_active,
    })
    setFormOpen(true)
  }

  const updateField = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  const closeForm = () => {
    setFormOpen(false)
    setEditingId(null)
  }

  const handleSave = () => {
    if (!form.name.trim()) {
      toast.error(t('validation.nameRequired'))
      return
    }
    if (!form.display_name.trim()) {
      toast.error(t('validation.displayNameRequired'))
      return
    }
    if (!form.transport) {
      toast.error(t('validation.transportRequired'))
      return
    }

    let envVars: Record<string, string> = {}
    if (form.env_vars.trim()) {
      try {
        const parsed: unknown = JSON.parse(form.env_vars)
        if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
          throw new Error('not a plain object')
        }
        envVars = parsed as Record<string, string>
      } catch {
        toast.error(t('validation.envVarsInvalid'))
        return
      }
    }

    const useStdio = form.transport === 'stdio'
    const command = useStdio ? form.command.trim() || null : null
    const url = useStdio ? null : form.url.trim() || null
    const apiKey = form.api_key.trim() || null
    const description = form.description.trim() || undefined

    if (editingId) {
      const payload: McpServerUpdatePayload = {
        display_name: form.display_name.trim(),
        description,
        transport: form.transport,
        command,
        url,
        api_key: apiKey,
        env_vars: envVars,
        is_active: form.is_active,
        priority: form.priority,
      }
      updateMut.mutate({ id: editingId, payload })
    } else {
      const payload: McpServerCreatePayload = {
        name: form.name.trim(),
        display_name: form.display_name.trim(),
        description,
        transport: form.transport,
        command,
        url,
        api_key: apiKey,
        env_vars: envVars,
        is_active: form.is_active,
        priority: form.priority,
      }
      createMut.mutate(payload)
    }
  }

  const handleDelete = async (server: McpServerItem) => {
    const ok = await confirm({
      title: t('actions.delete'),
      message: (
        <Trans
          i18nKey="confirm.deleteMessage"
          ns="adminMcpServer"
          values={{ name: server.display_name }}
          components={{ strong: <strong /> }}
        />
      ),
      confirmText: t('actions.confirm'),
      cancelText: t('actions.cancel'),
      variant: 'danger',
    })
    if (ok) deleteMut.mutate(server.id)
  }

  const submitting = createMut.isPending || updateMut.isPending
  const toggling = toggleMut.isPending

  return (
    <div className="space-y-4">
      {/* 页头 */}
      <div className="page-header">
        <div>
          <h1>{t('title')}</h1>
          <p className="text-muted">{t('subtitle')}</p>
        </div>
        <div className="action-group">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => queryClient.invalidateQueries({ queryKey: ['mcp-servers'] })}
            title={t('actions.refresh')}
          >
            <ICONS.refresh size={14} />
            {t('actions.refresh')}
          </button>
          <button type="button" className="btn btn-primary" onClick={handleCreate}>
            + {t('actions.addServer')}
          </button>
        </div>
      </div>

      {/* 搜索栏 */}
      <div className="toolbar">
        <div className="form-group" style={{ marginBottom: 0, flex: 1, maxWidth: 360 }}>
          <input
            type="text"
            placeholder={`${t('actions.search')}...`}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>

      {/* 列表 */}
      {isLoading ? (
        <Loading text={t('status.loading')} />
      ) : isError ? (
        <EmptyState
          title={t('errors.loadFailed')}
          description={getErrorMessage(error)}
          icon="empty"
          action={
            <button type="button" className="btn btn-secondary" onClick={() => refetch()}>
              {t('actions.retry')}
            </button>
          }
        />
      ) : filteredServers.length === 0 ? (
        <EmptyState
          title={t('empty.title')}
          description={t('empty.description')}
          icon="empty"
        />
      ) : (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>{t('table.name')}</th>
                <th>{t('table.displayName')}</th>
                <th>{t('table.transport')}</th>
                <th>{t('table.status')}</th>
                <th>{t('table.lastStatus')}</th>
                <th>{t('table.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {filteredServers.map((server) => (
                <tr key={server.id}>
                  <td>
                    <span className="font-medium">{server.name}</span>
                    {server.is_builtin && (
                      <span className="badge draft" style={{ marginLeft: 6 }}>
                        {t('badge.builtin')}
                      </span>
                    )}
                  </td>
                  <td>{server.display_name}</td>
                  <td>
                    <span className={transportBadgeClass(server.transport)}>
                      {t(`transports.${server.transport}`, { defaultValue: server.transport })}
                    </span>
                  </td>
                  <td>
                    {server.is_active ? (
                      <span className="badge success">{t('actions.enable')}</span>
                    ) : (
                      <span className="badge failed">{t('actions.disable')}</span>
                    )}
                  </td>
                  <td>
                    <LastStatusBadge status={server.last_status} />
                  </td>
                  <td>
                    <div className="action-group">
                      <button
                        type="button"
                        className="btn btn-sm btn-secondary"
                        onClick={() => toggleMut.mutate(server.id)}
                        disabled={toggling}
                      >
                        {server.is_active ? t('actions.disable') : t('actions.enable')}
                      </button>
                      <button
                        type="button"
                        className="btn btn-sm btn-secondary"
                        onClick={() => testMut.mutate(server.id)}
                        disabled={testingId === server.id}
                      >
                        {testingId === server.id ? t('actions.testing') : t('actions.test')}
                      </button>
                      <button
                        type="button"
                        className="btn btn-sm btn-secondary"
                        onClick={() => handleEdit(server)}
                      >
                        {t('actions.edit')}
                      </button>
                      {!server.is_builtin && (
                        <button
                          type="button"
                          className="btn btn-sm btn-danger"
                          onClick={() => handleDelete(server)}
                          disabled={deleteMut.isPending}
                        >
                          {t('actions.delete')}
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

      {/* 创建 / 编辑表单 */}
      {formOpen && (
        <McpServerForm
          form={form}
          updateField={updateField}
          transportOptions={transportOptions}
          editingId={editingId}
          submitting={submitting}
          onClose={closeForm}
          onSave={handleSave}
        />
      )}
    </div>
  )
}
