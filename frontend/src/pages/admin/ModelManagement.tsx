import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import Modal from '../../components/ui/Modal.tsx'
import Loading from '../../components/ui/Loading.tsx'
import EmptyState from '../../components/ui/EmptyState.tsx'
import { ICONS } from '../../components/ui/Icons.tsx'
import { getErrorMessage } from '../../utils/errors.ts'
import {
  listModelConfigs,
  createModelConfig,
  updateModelConfig,
  deleteModelConfig,
  toggleModelConfig,
  testModelConfig,
  setDefaultModelConfig,
  type ModelConfigItem,
  type ModelConfigCreatePayload,
} from '../../api/models.ts'

// --------------- Constants ---------------

const PROVIDERS = [
  { value: 'openai', label: 'OpenAI', apiBase: 'https://api.openai.com/v1' },
  { value: 'anthropic', label: 'Anthropic', apiBase: 'https://api.anthropic.com' },
  { value: 'google', label: 'Google', apiBase: 'https://generativelanguage.googleapis.com/v1beta' },
  { value: 'local', label: 'Local', apiBase: 'http://localhost:8080/v1' },
  { value: 'ollama', label: 'Ollama', apiBase: 'http://localhost:11434/v1' },
  { value: 'lmstudio', label: 'LM Studio', apiBase: 'http://localhost:1234/v1' },
] as const

const PROVIDER_COLORS: Record<string, string> = {
  openai: '#10a37f',
  anthropic: '#d97706',
  google: '#4285f4',
  local: '#6b7280',
  ollama: '#1e40af',
  lmstudio: '#7c3aed',
}

// --------------- Form Schema ---------------

const modelFormSchema = z.object({
  provider: z.string().min(1, '请选择供应商'),
  model_name: z.string().min(1, '请输入模型名称'),
  display_name: z.string().min(1, '请输入展示名称'),
  api_base: z.string().min(1, '请输入 API 端点'),
  api_key: z.string().optional(),
  is_default: z.boolean().default(false),
  is_active: z.boolean().default(true),
  temperature: z.coerce.number().min(0).max(2).default(0.7),
  max_tokens: z.coerce.number().min(1).max(128000).default(4096),
  top_p: z.coerce.number().min(0).max(1).default(0.9),
})

type ModelFormValues = z.infer<typeof modelFormSchema>

// Plain type matching what the form produces after defaults are applied
interface ModelFormData {
  provider: string
  model_name: string
  display_name: string
  api_base: string
  api_key?: string
  is_default: boolean
  is_active: boolean
  temperature: number
  max_tokens: number
  top_p: number
}

const EMPTY_FORM: ModelFormData = {
  provider: 'openai',
  model_name: '',
  display_name: '',
  api_base: 'https://api.openai.com/v1',
  api_key: '',
  is_default: false,
  is_active: true,
  temperature: 0.7,
  max_tokens: 4096,
  top_p: 0.9,
}

// --------------- Component ---------------

export default function ModelManagement() {
  const queryClient = useQueryClient()

  // Query params state
  const [search, setSearch] = useState('')
  const [providerFilter, setProviderFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [page, setPage] = useState(1)

  // Dialog state
  const [formOpen, setFormOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [testOpen, setTestOpen] = useState(false)
  const [testTarget, setTestTarget] = useState<ModelConfigItem | null>(null)
  const [testResult, setTestResult] = useState<{ success: boolean; message: string; result: string | null } | null>(null)
  const [testing, setTesting] = useState(false)
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null)

  const form = useForm<ModelFormData>({
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    resolver: zodResolver(modelFormSchema) as any,
    defaultValues: EMPTY_FORM,
  })

  // Query
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['model-configs', search, providerFilter, statusFilter, page],
    queryFn: () =>
      listModelConfigs({
        page,
        page_size: 20,
        search,
        provider: providerFilter,
        is_active: statusFilter,
      }).then((r) => r.data),
  })

  const items = data?.data?.items ?? []
  const total = data?.data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / 20))

  // Mutations
  const createMut = useMutation({
    mutationFn: (payload: ModelConfigCreatePayload) => createModelConfig(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['model-configs'] })
      setFormOpen(false)
    },
  })

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: string; data: ModelConfigCreatePayload }) =>
      updateModelConfig(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['model-configs'] })
      setFormOpen(false)
    },
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteModelConfig(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['model-configs'] })
      setDeleteConfirm(null)
    },
  })

  const toggleMut = useMutation({
    mutationFn: (id: string) => toggleModelConfig(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['model-configs'] }),
  })

  const setDefaultMut = useMutation({
    mutationFn: (id: string) => setDefaultModelConfig(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['model-configs'] }),
  })

  // Handlers
  const openCreate = () => {
    setEditingId(null)
    form.reset(EMPTY_FORM)
    setFormOpen(true)
  }

  const openEdit = (item: ModelConfigItem) => {
    setEditingId(item.id)
    form.reset({
      provider: item.provider,
      model_name: item.model_name,
      display_name: item.display_name,
      api_base: item.api_base,
      api_key: '',
      is_default: item.is_default,
      is_active: item.is_active,
      temperature: (item.parameters as Record<string, number> | null)?.temperature ?? 0.7,
      max_tokens: (item.parameters as Record<string, number> | null)?.max_tokens ?? 4096,
      top_p: (item.parameters as Record<string, number> | null)?.top_p ?? 0.9,
    })
    setFormOpen(true)
  }

  const onSubmit = (values: ModelFormValues) => {
    const payload: ModelConfigCreatePayload = {
      provider: values.provider,
      model_name: values.model_name,
      display_name: values.display_name,
      api_base: values.api_base,
      api_key: values.api_key || null,
      is_default: values.is_default,
      is_active: values.is_active,
      parameters: {
        temperature: values.temperature,
        max_tokens: values.max_tokens,
        top_p: values.top_p,
      },
    }
    if (editingId) {
      updateMut.mutate({ id: editingId, data: payload })
    } else {
      createMut.mutate(payload)
    }
  }

  const handleProviderChange = (provider: string) => {
    form.setValue('provider', provider)
    const preset = PROVIDERS.find((p) => p.value === provider)
    if (preset) {
      form.setValue('api_base', preset.apiBase)
    }
  }

  const handleTest = async (item: ModelConfigItem) => {
    setTestTarget(item)
    setTestOpen(true)
    setTestResult(null)
    setTesting(true)
    try {
      const res = await testModelConfig(item.id)
      setTestResult(res.data.data)
    } catch (err) {
      setTestResult({ success: false, message: getErrorMessage(err, '测试失败'), result: null })
    } finally {
      setTesting(false)
    }
  }

  const submitLabel = editingId ? '保存' : '创建'
  const mutError =
    createMut.error || updateMut.error
      ? getErrorMessage(createMut.error || updateMut.error, '操作失败')
      : ''

  // Reset page on filter change
  useEffect(() => {
    setPage(1)
  }, [search, providerFilter, statusFilter])

  return (
    <div className="admin-model-management">
      {/* Header */}
      <div className="admin-page-header">
        <h1 className="admin-page-title">模型管理</h1>
        <p className="admin-page-desc">管理 AI 模型配置，包括供应商、API 端点、密钥和默认模型设置。</p>
      </div>

      {/* Toolbar */}
      <div className="admin-toolbar">
        <div className="admin-toolbar-left">
          <div className="admin-search-box">
            <ICONS.search size={14} />
            <input
              type="text"
              placeholder="搜索模型名称..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="admin-search-input"
            />
          </div>
          <select
            value={providerFilter}
            onChange={(e) => setProviderFilter(e.target.value)}
            className="admin-filter-select"
          >
            <option value="">全部供应商</option>
            {PROVIDERS.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="admin-filter-select"
          >
            <option value="">全部状态</option>
            <option value="active">已启用</option>
            <option value="inactive">已禁用</option>
          </select>
        </div>
        <div className="admin-toolbar-right">
          <button className="btn btn-primary" onClick={openCreate}>
            <ICONS.dashboard size={14} /> 添加模型
          </button>
        </div>
      </div>

      {/* Content */}
      {isLoading ? (
        <Loading />
      ) : isError ? (
        <div className="admin-error">{getErrorMessage(error, '加载模型列表失败')}</div>
      ) : items.length === 0 ? (
        <EmptyState title="暂无模型配置" />
      ) : (
        <>
          <div className="admin-table-wrapper">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>展示名称</th>
                  <th>供应商</th>
                  <th>模型名称</th>
                  <th>API 端点</th>
                  <th style={{ width: 70, textAlign: 'center' }}>默认</th>
                  <th style={{ width: 80, textAlign: 'center' }}>状态</th>
                  <th style={{ width: 180, textAlign: 'right' }}>操作</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id}>
                    <td className="admin-table-name">
                      <span className="admin-model-display">{item.display_name}</span>
                    </td>
                    <td>
                      <span
                        className="admin-provider-badge"
                        style={{
                          backgroundColor: PROVIDER_COLORS[item.provider] || '#6b7280',
                        }}
                      >
                        {PROVIDERS.find((p) => p.value === item.provider)?.label || item.provider}
                      </span>
                    </td>
                    <td className="admin-table-mono">{item.model_name}</td>
                    <td className="admin-table-mono" style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {item.api_base}
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      {item.is_default ? (
                        <span title="默认模型" style={{ color: '#f59e0b', fontSize: 18 }}>
                          ★
                        </span>
                      ) : (
                        <button
                          className="admin-icon-btn"
                          title="设为默认"
                          onClick={() => setDefaultMut.mutate(item.id)}
                        >
                          <ICONS.check size={14} />
                        </button>
                      )}
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      <button
                        className={`admin-toggle ${item.is_active ? 'active' : ''}`}
                        onClick={() => toggleMut.mutate(item.id)}
                        title={item.is_active ? '已启用，点击禁用' : '已禁用，点击启用'}
                      >
                        <span className="admin-toggle-knob" />
                      </button>
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <div className="admin-actions">
                        <button
                          className="admin-action-btn"
                          title="测试连接"
                          onClick={() => handleTest(item)}
                        >
                          <ICONS.send size={14} />
                        </button>
                        <button
                          className="admin-action-btn"
                          title="编辑"
                          onClick={() => openEdit(item)}
                        >
                          <ICONS.settings size={14} />
                        </button>
                        <button
                          className="admin-action-btn danger"
                          title="删除"
                          onClick={() => setDeleteConfirm(item.id)}
                        >
                          <ICONS.close size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="admin-pagination">
              <button disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
                上一页
              </button>
              <span>
                {page} / {totalPages}（共 {total} 条）
              </span>
              <button disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
                下一页
              </button>
            </div>
          )}
        </>
      )}

      {/* Create/Edit Dialog */}
      {formOpen && (
        <Modal
          title={editingId ? '编辑模型配置' : '新建模型配置'}
          onClose={() => setFormOpen(false)}
          footer={
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button className="btn btn-secondary" onClick={() => setFormOpen(false)}>
                取消
              </button>
              <button
                className="btn btn-primary"
                onClick={form.handleSubmit(onSubmit)}
                disabled={createMut.isPending || updateMut.isPending}
              >
                {createMut.isPending || updateMut.isPending ? '保存中...' : submitLabel}
              </button>
            </div>
          }
        >
          <form className="admin-form" onSubmit={form.handleSubmit(onSubmit)}>
            {mutError && <div className="admin-form-error">{mutError}</div>}

            <div className="admin-form-row">
              <label className="admin-form-label">供应商</label>
              <select
                className="admin-form-select"
                {...form.register('provider')}
                onChange={(e) => handleProviderChange(e.target.value)}
              >
                {PROVIDERS.map((p) => (
                  <option key={p.value} value={p.value}>
                    {p.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="admin-form-row">
              <label className="admin-form-label">展示名称</label>
              <input className="admin-form-input" {...form.register('display_name')} placeholder="如 GPT-4o" />
            </div>

            <div className="admin-form-row">
              <label className="admin-form-label">模型名称</label>
              <input className="admin-form-input" {...form.register('model_name')} placeholder="如 gpt-4o" />
            </div>

            <div className="admin-form-row">
              <label className="admin-form-label">API 端点</label>
              <input className="admin-form-input" {...form.register('api_base')} placeholder="https://api.openai.com/v1" />
            </div>

            <div className="admin-form-row">
              <label className="admin-form-label">
                API Key {editingId && <span className="admin-form-hint">（留空表示不修改）</span>}
              </label>
              <input
                className="admin-form-input"
                type="password"
                {...form.register('api_key')}
                placeholder={editingId ? '留空保持不变' : '输入 API Key'}
              />
            </div>

            <div className="admin-form-row">
              <label className="admin-form-label">参数</label>
              <div className="admin-form-inline">
                <div className="admin-form-field">
                  <span>Temperature</span>
                  <input
                    type="number"
                    step="0.1"
                    min="0"
                    max="2"
                    className="admin-form-input-sm"
                    {...form.register('temperature')}
                  />
                </div>
                <div className="admin-form-field">
                  <span>Max Tokens</span>
                  <input
                    type="number"
                    min="1"
                    max="128000"
                    className="admin-form-input-sm"
                    {...form.register('max_tokens')}
                  />
                </div>
                <div className="admin-form-field">
                  <span>Top P</span>
                  <input
                    type="number"
                    step="0.1"
                    min="0"
                    max="1"
                    className="admin-form-input-sm"
                    {...form.register('top_p')}
                  />
                </div>
              </div>
            </div>

            <div className="admin-form-row">
              <label className="admin-form-checkbox">
                <input type="checkbox" {...form.register('is_default')} />
                <span>设为默认模型</span>
              </label>
            </div>
          </form>
        </Modal>
      )}

      {/* Test Connection Dialog */}
      {testOpen && testTarget && (
        <Modal title={`测试连接 — ${testTarget.display_name}`} onClose={() => setTestOpen(false)}>
          <div className="admin-test-body">
            <div className="admin-test-info">
              <span className="admin-test-label">供应商：</span>
              {PROVIDERS.find((p) => p.value === testTarget.provider)?.label || testTarget.provider}
            </div>
            <div className="admin-test-info">
              <span className="admin-test-label">模型：</span>
              {testTarget.model_name}
            </div>

            {testing ? (
              <div className="admin-test-loading">
                <Loading />
                <span>正在测试连接...</span>
              </div>
            ) : testResult ? (
              <div className={`admin-test-result ${testResult.success ? 'success' : 'error'}`}>
                <div className="admin-test-result-header">
                  {testResult.success ? (
                    <>
                      <ICONS.check size={18} />
                      <span style={{ color: '#16a34a' }}>连接成功</span>
                    </>
                  ) : (
                    <>
                      <ICONS.close size={18} />
                      <span style={{ color: '#dc2626' }}>连接失败</span>
                    </>
                  )}
                </div>
                <div className="admin-test-result-msg">{testResult.message}</div>
                {testResult.result && (
                  <pre className="admin-test-result-output">{testResult.result}</pre>
                )}
              </div>
            ) : null}
          </div>
        </Modal>
      )}

      {/* Delete Confirm Dialog */}
      {deleteConfirm && (
        <Modal title="确认删除" onClose={() => setDeleteConfirm(null)}>
          <p style={{ marginBottom: 16 }}>确定要删除此模型配置吗？此操作不可撤销。</p>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button className="btn btn-secondary" onClick={() => setDeleteConfirm(null)}>
              取消
            </button>
            <button
              className="btn btn-danger"
              onClick={() => deleteMut.mutate(deleteConfirm)}
              disabled={deleteMut.isPending}
            >
              {deleteMut.isPending ? '删除中...' : '确认删除'}
            </button>
          </div>
          {deleteMut.error && (
            <div className="admin-form-error" style={{ marginTop: 8 }}>
              {getErrorMessage(deleteMut.error, '删除失败')}
            </div>
          )}
        </Modal>
      )}
    </div>
  )
}
