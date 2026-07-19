import { useEffect, useState } from 'react'
import Modal from '../components/ui/Modal.tsx'
import ConfirmDialog from '../components/ui/ConfirmDialog.tsx'
import Loading from '../components/ui/Loading.tsx'
import EmptyState from '../components/ui/EmptyState.tsx'
import { toast } from '../components/ui/Toaster.tsx'
import { api } from '../api/client.ts'
import { getErrorMessage } from '../utils/errors.ts'
import type { DataResponse, PaginatedResponse } from '../types/report.ts'
import type {
  LlmModel,
  LlmProvider,
  ModelForm,
  ModelTier,
  ProviderForm,
  ProviderTestResult,
  ProviderType,
} from '../types/llmProvider.ts'

const EMPTY_PROVIDER_FORM: ProviderForm = {
  name: '',
  provider_type: 'ollama',
  base_url: 'http://localhost:11434',
  api_key: '',
  is_default: false,
  is_active: true,
}

const EMPTY_MODEL_FORM: ModelForm = {
  model_name: '',
  display_name: '',
  tier: '',
  is_active: true,
}

// 常用厂商快捷预设：点击后自动填充表单
// 用户无需手动查找 base_url，提升配置体验
const VENDOR_PRESETS: Array<{
  key: string
  label: string
  provider_type: ProviderType
  base_url: string
  default_name: string
  sample_model?: string
  hint: string
}> = [
  {
    key: 'ollama',
    label: 'Ollama',
    provider_type: 'ollama',
    base_url: 'http://localhost:11434',
    default_name: '本地 Ollama',
    sample_model: 'llama3.1',
    hint: '本地部署，无需 Key',
  },
  {
    key: 'openai',
    label: 'OpenAI',
    provider_type: 'openai',
    base_url: 'https://api.openai.com/v1',
    default_name: 'OpenAI',
    sample_model: 'gpt-4o-mini',
    hint: '官方 API',
  },
  {
    key: 'siliconflow',
    label: 'SiliconFlow',
    provider_type: 'openai',
    base_url: 'https://api.siliconflow.cn/v1',
    default_name: 'SiliconFlow',
    sample_model: 'Qwen/Qwen2.5-7B-Instruct',
    hint: '硅基流动',
  },
  {
    key: 'deepseek',
    label: 'DeepSeek',
    provider_type: 'openai',
    base_url: 'https://api.deepseek.com/v1',
    default_name: 'DeepSeek',
    sample_model: 'deepseek-chat',
    hint: '深度求索',
  },
  {
    key: 'moonshot',
    label: 'Moonshot',
    provider_type: 'openai',
    base_url: 'https://api.moonshot.cn/v1',
    default_name: 'Moonshot (Kimi)',
    sample_model: 'moonshot-v1-8k',
    hint: '月之暗面',
  },
  {
    key: 'zhipu',
    label: 'Zhipu AI',
    provider_type: 'openai',
    base_url: 'https://open.bigmodel.cn/api/paas/v4',
    default_name: 'Zhipu (智谱)',
    sample_model: 'glm-4-flash',
    hint: '智谱清言',
  },
  {
    key: '587lol',
    label: '587.lol',
    provider_type: 'openai',
    base_url: 'https://api.587.lol/v1',
    default_name: '587.lol Free',
    sample_model: 'moonweaver-4.8',
    hint: '免费聚合',
  },
  {
    key: 'custom',
    label: '自定义',
    provider_type: 'openai',
    base_url: '',
    default_name: '',
    hint: 'OpenAI 兼容',
  },
]

export default function LlmProvidersPage() {
  const [providers, setProviders] = useState<LlmProvider[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [providerModalOpen, setProviderModalOpen] = useState(false)
  const [editingProvider, setEditingProvider] = useState<LlmProvider | null>(null)
  const [providerForm, setProviderForm] = useState<ProviderForm>(EMPTY_PROVIDER_FORM)
  const [submitting, setSubmitting] = useState(false)
  const [actingId, setActingId] = useState<string | null>(null)
  const [deleteProviderTarget, setDeleteProviderTarget] = useState<LlmProvider | null>(null)
  // 模型管理弹窗
  const [modelsProvider, setModelsProvider] = useState<LlmProvider | null>(null)

  const fetchProviders = async () => {
    setLoading(true)
    setError('')
    try {
      const response = await api.get<DataResponse<PaginatedResponse<LlmProvider>>>(
        '/llm-providers',
        { params: { page: 1, page_size: 100 } },
      )
      setProviders(response.data.data?.items || [])
    } catch (err) {
      setError(getErrorMessage(err, '加载供应商列表失败'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchProviders()
  }, [])

  const openCreateProvider = () => {
    setEditingProvider(null)
    setProviderForm(EMPTY_PROVIDER_FORM)
    setProviderModalOpen(true)
  }

  const openEditProvider = (provider: LlmProvider) => {
    setEditingProvider(provider)
    setProviderForm({
      name: provider.name,
      provider_type: provider.provider_type,
      base_url: provider.base_url,
      api_key: '',
      is_default: provider.is_default,
      is_active: provider.is_active,
    })
    setProviderModalOpen(true)
  }

  const handleSaveProvider = async () => {
    setSubmitting(true)
    setError('')
    try {
      // 更新时 api_key 留空表示不改；创建时留空表示不设
      const payload: Record<string, unknown> = {
        name: providerForm.name,
        provider_type: providerForm.provider_type,
        base_url: providerForm.base_url,
        is_default: providerForm.is_default,
        is_active: providerForm.is_active,
      }
      if (providerForm.api_key) {
        payload.api_key = providerForm.api_key
      }
      if (editingProvider) {
        const response = await api.put<DataResponse<LlmProvider>>(
          `/llm-providers/${editingProvider.id}`,
          payload,
        )
        const updated = response.data.data
        if (updated) {
          setProviders((prev) =>
            prev.map((p) => (p.id === editingProvider.id ? { ...p, ...updated } : p)),
          )
        }
      } else {
        const response = await api.post<DataResponse<LlmProvider>>('/llm-providers', payload)
        const created = response.data.data
        if (created) {
          setProviders((prev) => [created, ...prev])
        }
      }
      setProviderModalOpen(false)
    } catch (err) {
      setError(getErrorMessage(err, '保存供应商失败'))
    } finally {
      setSubmitting(false)
    }
  }

  const handleDeleteProvider = async (provider: LlmProvider) => {
    setActingId(provider.id)
    setError('')
    try {
      await api.delete(`/llm-providers/${provider.id}`)
      setProviders((prev) => prev.filter((p) => p.id !== provider.id))
      toast.success('供应商已删除', `「${provider.name}」及其所有模型已删除。`)
      setDeleteProviderTarget(null)
    } catch (err) {
      setError(getErrorMessage(err, '删除供应商失败'))
    } finally {
      setActingId(null)
    }
  }

  const handleTestProvider = async (provider: LlmProvider) => {
    setActingId(provider.id)
    setError('')
    try {
      const response = await api.post<DataResponse<ProviderTestResult>>(
        `/llm-providers/${provider.id}/test`,
      )
      const result = response.data.data
      if (result) {
        setProviders((prev) =>
          prev.map((p) =>
            p.id === provider.id
              ? {
                  ...p,
                  last_tested_at: result.tested_at,
                  last_test_ok: result.ok,
                  last_test_message: result.message,
                }
              : p,
          ),
        )
      }
    } catch (err) {
      setError(getErrorMessage(err, '连通性测试失败'))
    } finally {
      setActingId(null)
    }
  }

  return (
    <div className="container">
      <div className="page-header">
        <h1>模型供应商管理</h1>
        <button type="button" onClick={openCreateProvider}>新建供应商</button>
      </div>

      {error && (
        <div className="alert alert-error mb-4" role="alert">
          {error}
        </div>
      )}

      {loading ? (
        <Loading text="加载供应商中..." />
      ) : providers.length === 0 ? (
        <EmptyState
          title="暂无模型供应商"
          description="点击「新建供应商」添加第一个 LLM 服务。未配置时系统回退到 .env 默认配置。"
        />
      ) : (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>名称</th>
                <th>类型</th>
                <th>服务地址</th>
                <th>API Key</th>
                <th>状态</th>
                <th>连通性</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {providers.map((provider) => (
                <tr key={provider.id}>
                  <td>
                    {provider.name}
                    {provider.is_default && <span className="badge success ml-2">默认</span>}
                  </td>
                  <td>{provider.provider_type === 'ollama' ? 'Ollama' : 'OpenAI 兼容'}</td>
                  <td className="text-sm text-muted">{provider.base_url}</td>
                  <td>
                    {provider.has_api_key ? (
                      <span className="badge success">已配置</span>
                    ) : (
                      <span className="text-muted">—</span>
                    )}
                  </td>
                  <td>
                    {provider.is_active ? (
                      <span className="badge success">启用</span>
                    ) : (
                      <span className="badge rejected">停用</span>
                    )}
                  </td>
                  <td>
                    {provider.last_test_ok === null ? (
                      <span className="text-muted">未测试</span>
                    ) : provider.last_test_ok ? (
                      <span className="text-sm" title={provider.last_test_message || ''}>
                        正常
                      </span>
                    ) : (
                      <span
                        className="text-sm"
                        style={{ color: 'var(--color-danger)' }}
                        title={provider.last_test_message || ''}
                      >
                        异常
                      </span>
                    )}
                  </td>
                  <td>
                    <div className="action-group">
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => handleTestProvider(provider)}
                        disabled={actingId === provider.id}
                      >
                        {actingId === provider.id ? '测试中...' : '测试'}
                      </button>
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => setModelsProvider(provider)}
                      >
                        模型
                      </button>
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => openEditProvider(provider)}
                      >
                        编辑
                      </button>
                      <button
                        type="button"
                        className="danger"
                        onClick={() => setDeleteProviderTarget(provider)}
                        disabled={actingId === provider.id}
                      >
                        删除
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {providerModalOpen && (
        <ProviderModal
          editing={editingProvider}
          form={providerForm}
          onFormChange={setProviderForm}
          onSubmit={handleSaveProvider}
          onClose={() => setProviderModalOpen(false)}
          submitting={submitting}
        />
      )}

      {modelsProvider && (
        <ModelsModal
          provider={modelsProvider}
          onClose={() => setModelsProvider(null)}
        />
      )}

      <ConfirmDialog
        open={!!deleteProviderTarget}
        title="确认删除供应商"
        message={
          deleteProviderTarget ? (
            <>
              确定要删除供应商「<strong>{deleteProviderTarget.name}</strong>」吗？
              <br />
              <span style={{ color: 'var(--color-text-muted)', fontSize: '0.8125rem' }}>
                其下所有模型将一并删除，此操作不可恢复。
              </span>
            </>
          ) : null
        }
        confirmText="确认删除"
        variant="danger"
        onConfirm={async () => {
          if (deleteProviderTarget) {
            await handleDeleteProvider(deleteProviderTarget)
          }
        }}
        onCancel={() => setDeleteProviderTarget(null)}
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// 供应商创建/编辑弹窗
// ---------------------------------------------------------------------------

interface ProviderModalProps {
  editing: LlmProvider | null
  form: ProviderForm
  onFormChange: (form: ProviderForm) => void
  onSubmit: () => void
  onClose: () => void
  submitting: boolean
}

function ProviderModal({
  editing,
  form,
  onFormChange,
  onSubmit,
  onClose,
  submitting,
}: ProviderModalProps) {
  // 当前选中的预设 key（用于高亮）—— 根据 base_url+provider_type 反推
  const activePresetKey = VENDOR_PRESETS.find(
    (p) => p.base_url && p.base_url === form.base_url && p.provider_type === form.provider_type,
  )?.key

  const applyPreset = (preset: (typeof VENDOR_PRESETS)[number]) => {
    onFormChange({
      ...form,
      name: form.name || preset.default_name,
      provider_type: preset.provider_type,
      base_url: preset.base_url,
    })
  }

  return (
    <Modal
      title={editing ? '编辑供应商' : '新建供应商'}
      onClose={onClose}
      footer={
        <>
          <button type="button" className="secondary" onClick={onClose}>
            取消
          </button>
          <button
            type="button"
            onClick={onSubmit}
            disabled={submitting || !form.name || !form.base_url}
          >
            {submitting ? '保存中...' : '保存'}
          </button>
        </>
      }
    >
      {/* 厂商快捷预设：点击后自动填充表单字段 */}
      <div className="form-group">
        <label>常用厂商快捷选择</label>
        <div
          className="vendor-preset-grid"
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(110px, 1fr))',
            gap: 'var(--space-2)',
            marginBottom: 'var(--space-1)',
          }}
        >
          {VENDOR_PRESETS.map((preset) => {
            const active = activePresetKey === preset.key
            return (
              <button
                key={preset.key}
                type="button"
                className={active ? '' : 'secondary'}
                onClick={() => applyPreset(preset)}
                title={preset.hint}
                style={{
                  padding: '6px 8px',
                  fontSize: '0.75rem',
                  justifyContent: 'center',
                  ...(active
                    ? { boxShadow: '0 0 0 2px var(--color-primary-ink) inset' }
                    : {}),
                }}
              >
                {preset.label}
              </button>
            )
          })}
        </div>
        <p
          className="text-muted"
          style={{ fontSize: '0.6875rem', marginTop: 'var(--space-1)' }}
        >
          点击预设自动填充名称 / 类型 / 服务地址。如需自定义可直接修改下方字段。
        </p>
      </div>

      <div className="form-group">
        <label htmlFor="provider-name">名称</label>
        <input
          id="provider-name"
          value={form.name}
          onChange={(e) => onFormChange({ ...form, name: e.target.value })}
          placeholder="便于识别，如「本地 Ollama」"
        />
      </div>
      <div className="form-group">
        <label htmlFor="provider-type">供应商类型</label>
        <select
          id="provider-type"
          value={form.provider_type}
          onChange={(e) =>
            onFormChange({ ...form, provider_type: e.target.value as ProviderType })
          }
        >
          <option value="ollama">Ollama（本地）</option>
          <option value="openai">OpenAI 兼容（云端）</option>
        </select>
      </div>
      <div className="form-group">
        <label htmlFor="provider-url">服务地址</label>
        <input
          id="provider-url"
          value={form.base_url}
          onChange={(e) => onFormChange({ ...form, base_url: e.target.value })}
          placeholder="http://localhost:11434 或 https://api.example.com/v1"
        />
      </div>
      <div className="form-group">
        <label htmlFor="provider-key">
          API Key
          {editing && (
            <span className="text-muted text-sm ml-2">（留空表示不修改）</span>
          )}
        </label>
        <input
          id="provider-key"
          type="password"
          value={form.api_key}
          onChange={(e) => onFormChange({ ...form, api_key: e.target.value })}
          placeholder={form.provider_type === 'ollama' ? 'Ollama 无需 API Key' : 'sk-...'}
        />
      </div>
      <div className="form-group">
        <label>
          <input
            type="checkbox"
            checked={form.is_default}
            onChange={(e) => onFormChange({ ...form, is_default: e.target.checked })}
          />{' '}
          设为默认供应商（全局唯一，设为默认后将自动取消其他默认）
        </label>
      </div>
      <div className="form-group">
        <label>
          <input
            type="checkbox"
            checked={form.is_active}
            onChange={(e) => onFormChange({ ...form, is_active: e.target.checked })}
          />{' '}
          启用
        </label>
      </div>
    </Modal>
  )
}

// ---------------------------------------------------------------------------
// 模型管理弹窗
// ---------------------------------------------------------------------------

interface ModelsModalProps {
  provider: LlmProvider
  onClose: () => void
}

function ModelsModal({ provider, onClose }: ModelsModalProps) {
  const [models, setModels] = useState<LlmModel[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [modelFormOpen, setModelFormOpen] = useState(false)
  const [editingModel, setEditingModel] = useState<LlmModel | null>(null)
  const [modelForm, setModelForm] = useState<ModelForm>(EMPTY_MODEL_FORM)
  const [submitting, setSubmitting] = useState(false)
  const [actingId, setActingId] = useState<string | null>(null)
  const [deleteModelTarget, setDeleteModelTarget] = useState<LlmModel | null>(null)

  const fetchModels = async () => {
    setLoading(true)
    setError('')
    try {
      const response = await api.get<DataResponse<{ items: LlmModel[] }>>(
        `/llm-providers/${provider.id}/models`,
      )
      setModels(response.data.data?.items || [])
    } catch (err) {
      setError(getErrorMessage(err, '加载模型列表失败'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchModels()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const openCreateModel = () => {
    setEditingModel(null)
    setModelForm(EMPTY_MODEL_FORM)
    setModelFormOpen(true)
  }

  const openEditModel = (model: LlmModel) => {
    setEditingModel(model)
    setModelForm({
      model_name: model.model_name,
      display_name: model.display_name,
      tier: model.tier || '',
      is_active: model.is_active,
    })
    setModelFormOpen(true)
  }

  const handleSaveModel = async () => {
    setSubmitting(true)
    setError('')
    try {
      const tier = modelForm.tier || null
      const payload: Record<string, unknown> = {
        model_name: modelForm.model_name,
        display_name: modelForm.display_name,
        tier,
        is_active: modelForm.is_active,
      }
      if (editingModel) {
        const response = await api.put<DataResponse<LlmModel>>(
          `/llm-providers/models/${editingModel.id}`,
          payload,
        )
        const updated = response.data.data
        if (updated) {
          setModels((prev) =>
            prev.map((m) => (m.id === editingModel.id ? { ...m, ...updated } : m)),
          )
        }
      } else {
        const response = await api.post<DataResponse<LlmModel>>(
          `/llm-providers/${provider.id}/models`,
          payload,
        )
        const created = response.data.data
        if (created) {
          setModels((prev) => [...prev, created])
        }
      }
      setModelFormOpen(false)
    } catch (err) {
      setError(getErrorMessage(err, '保存模型失败'))
    } finally {
      setSubmitting(false)
    }
  }

  const handleDeleteModel = async (model: LlmModel) => {
    setActingId(model.id)
    setError('')
    try {
      await api.delete(`/llm-providers/models/${model.id}`)
      setModels((prev) => prev.filter((m) => m.id !== model.id))
      toast.success('模型已删除', `「${model.display_name}」已删除。`)
      setDeleteModelTarget(null)
    } catch (err) {
      const msg = getErrorMessage(err, '删除模型失败')
      setError(msg)
      toast.error(msg)
    } finally {
      setActingId(null)
    }
  }

  return (
    <Modal
      title={`模型管理 — ${provider.name}`}
      onClose={onClose}
      footer={
        <button type="button" onClick={onClose}>关闭</button>
      }
    >
      {error && <div className="alert alert-error mb-3">{error}</div>}

      <div className="page-header" style={{ marginBottom: '1rem' }}>
        <p className="text-muted text-sm">
          供应商下可用模型列表。tier 对应模型路由档位，留空表示不参与档位路由。
        </p>
        <button type="button" onClick={openCreateModel}>添加模型</button>
      </div>

      {loading ? (
        <Loading text="加载模型中..." />
      ) : models.length === 0 ? (
        <EmptyState title="暂无模型" description="点击「添加模型」配置第一个可用模型。" />
      ) : (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>模型标识</th>
                <th>展示名称</th>
                <th>路由档位</th>
                <th>状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {models.map((model) => (
                <tr key={model.id}>
                  <td className="text-sm">{model.model_name}</td>
                  <td>{model.display_name}</td>
                  <td>
                    {model.tier ? (
                      <span className="badge">{model.tier}</span>
                    ) : (
                      <span className="text-muted">—</span>
                    )}
                  </td>
                  <td>
                    {model.is_active ? (
                      <span className="badge success">启用</span>
                    ) : (
                      <span className="badge rejected">停用</span>
                    )}
                  </td>
                  <td>
                    <div className="action-group">
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => openEditModel(model)}
                      >
                        编辑
                      </button>
                      <button
                        type="button"
                        className="danger"
                        onClick={() => setDeleteModelTarget(model)}
                        disabled={actingId === model.id}
                      >
                        删除
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {modelFormOpen && (
        <Modal
          title={editingModel ? '编辑模型' : '添加模型'}
          onClose={() => setModelFormOpen(false)}
          footer={
            <>
              <button type="button" className="secondary" onClick={() => setModelFormOpen(false)}>
                取消
              </button>
              <button
                type="button"
                onClick={handleSaveModel}
                disabled={
                  submitting || !modelForm.model_name || !modelForm.display_name
                }
              >
                {submitting ? '保存中...' : '保存'}
              </button>
            </>
          }
        >
          <div className="form-group">
            <label htmlFor="model-name">模型标识</label>
            <input
              id="model-name"
              value={modelForm.model_name}
              onChange={(e) => onModelFormChange(setModelForm, modelForm, 'model_name', e.target.value)}
              placeholder="如 qwen2.5:7b、gpt-4o"
            />
          </div>
          <div className="form-group">
            <label htmlFor="model-display">展示名称</label>
            <input
              id="model-display"
              value={modelForm.display_name}
              onChange={(e) => onModelFormChange(setModelForm, modelForm, 'display_name', e.target.value)}
              placeholder="便于识别的名称"
            />
          </div>
          <div className="form-group">
            <label htmlFor="model-tier">路由档位</label>
            <select
              id="model-tier"
              value={modelForm.tier}
              onChange={(e) =>
                onModelFormChange(
                  setModelForm,
                  modelForm,
                  'tier',
                  e.target.value as ModelTier | '',
                )
              }
            >
              <option value="">不参与路由</option>
              <option value="low">low（轻量任务）</option>
              <option value="medium">medium（主力模型）</option>
              <option value="high">high（复杂推理）</option>
            </select>
          </div>
          <div className="form-group">
            <label>
              <input
                type="checkbox"
                checked={modelForm.is_active}
                onChange={(e) =>
                  onModelFormChange(setModelForm, modelForm, 'is_active', e.target.checked)
                }
              />{' '}
              启用
            </label>
          </div>
        </Modal>
      )}

      <ConfirmDialog
        open={!!deleteModelTarget}
        title="确认删除模型"
        message={
          deleteModelTarget ? (
            <>
              确定要删除模型「<strong>{deleteModelTarget.display_name}</strong>」吗？
            </>
          ) : null
        }
        confirmText="确认删除"
        variant="danger"
        onConfirm={async () => {
          if (deleteModelTarget) {
            await handleDeleteModel(deleteModelTarget)
          }
        }}
        onCancel={() => setDeleteModelTarget(null)}
      />
    </Modal>
  )
}

function onModelFormChange(
  setter: (form: ModelForm) => void,
  current: ModelForm,
  field: keyof ModelForm,
  value: string | boolean,
) {
  setter({ ...current, [field]: value })
}
