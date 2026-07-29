import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import Modal from '../components/ui/Modal.tsx'
import ConfirmDialog from '../components/ui/ConfirmDialog.tsx'
import Loading from '../components/ui/Loading.tsx'
import EmptyState from '../components/ui/EmptyState.tsx'
import { ICONS } from '../components/ui/Icons.tsx'
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
// label / hint / default_name / sample_model 视作厂商数据，保留字面量
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
  const { t } = useTranslation()
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
  const [keyword, setKeyword] = useState('')

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
      setError(getErrorMessage(err, t('common:llmProviders.loadFailed')))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchProviders()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 客户端关键词过滤：按 name / base_url / provider_type 匹配
  const filteredProviders = useMemo(() => {
    const kw = keyword.trim().toLowerCase()
    if (!kw) return providers
    return providers.filter(
      (p) =>
        (p.name || '').toLowerCase().includes(kw) ||
        (p.base_url || '').toLowerCase().includes(kw) ||
        (p.provider_type || '').toLowerCase().includes(kw),
    )
  }, [providers, keyword])

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
        toast.success(t('common:llmProviders.toastUpdated'))
      } else {
        const response = await api.post<DataResponse<LlmProvider>>('/llm-providers', payload)
        const created = response.data.data
        if (created) {
          setProviders((prev) => [created, ...prev])
        }
        toast.success(t('common:llmProviders.toastCreated'))
      }
      setProviderModalOpen(false)
    } catch (err) {
      const msg = getErrorMessage(err, t('common:llmProviders.saveFailed'))
      setError(msg)
      toast.error(t('common:llmProviders.saveFailed'), msg)
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
      toast.success(
        t('common:llmProviders.toastDeleted'),
        t('common:llmProviders.toastDeletedDesc', { name: provider.name }),
      )
      setDeleteProviderTarget(null)
    } catch (err) {
      const msg = getErrorMessage(err, t('common:llmProviders.deleteFailed'))
      setError(msg)
      toast.error(t('common:llmProviders.deleteFailed'), msg)
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
        if (result.ok) {
          toast.success(
            t('common:llmProviders.toastTestOk'),
            t('common:llmProviders.toastTestOkDesc', { name: provider.name }),
          )
        } else {
          toast.error(
            t('common:llmProviders.toastTestFail'),
            result.message ||
              t('common:llmProviders.toastTestFailDesc', { name: provider.name }),
          )
        }
      }
    } catch (err) {
      const msg = getErrorMessage(err, t('common:llmProviders.testFailed'))
      setError(msg)
      toast.error(t('common:llmProviders.toastTestFail'), msg)
    } finally {
      setActingId(null)
    }
  }

  return (
    <div className="container">
      <div className="page-header">
        <h1>{t('common:llmProviders.title')}</h1>
        <button type="button" onClick={openCreateProvider}>
          {t('common:llmProviders.create')}
        </button>
      </div>

      {error && (
        <div className="alert alert-error mb-4" role="alert">
          <span>{error}</span>
          <button type="button" className="chat-error-retry" onClick={fetchProviders}>
            {t('common:llmProviders.retry')}
          </button>
        </div>
      )}

      {providers.length > 0 && (
        <div className="toolbar">
          <div className="search-inline">
            <ICONS.search size={14} />
            <input
              type="search"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              placeholder={t('common:llmProviders.searchPlaceholder')}
              aria-label={t('common:llmProviders.searchPlaceholder')}
            />
          </div>
        </div>
      )}

      {loading ? (
        <Loading text={t('common:llmProviders.loading')} />
      ) : providers.length === 0 ? (
        <EmptyState
          icon="llm"
          title={t('common:llmProviders.emptyTitle')}
          description={t('common:llmProviders.emptyDesc')}
          action={
            <button type="button" onClick={openCreateProvider}>
              {t('common:llmProviders.create')}
            </button>
          }
        />
      ) : filteredProviders.length === 0 ? (
        <EmptyState
          icon="search"
          title={t('common:llmProviders.emptySearchTitle')}
          description={t('common:llmProviders.emptySearchDesc')}
        />
      ) : (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>{t('common:llmProviders.colName')}</th>
                <th>{t('common:llmProviders.colType')}</th>
                <th>{t('common:llmProviders.colBaseUrl')}</th>
                <th>{t('common:llmProviders.colApiKey')}</th>
                <th>{t('common:llmProviders.colStatus')}</th>
                <th>{t('common:llmProviders.colConnectivity')}</th>
                <th>{t('common:llmProviders.colActions')}</th>
              </tr>
            </thead>
            <tbody>
              {filteredProviders.map((provider) => (
                <tr key={provider.id}>
                  <td>
                    {provider.name}
                    {provider.is_default && (
                      <span className="badge success ml-2">
                        {t('common:llmProviders.defaultBadge')}
                      </span>
                    )}
                  </td>
                  <td>
                    {provider.provider_type === 'ollama'
                      ? t('common:llmProviders.typeOllama')
                      : t('common:llmProviders.typeOpenAi')}
                  </td>
                  <td className="text-sm text-muted">{provider.base_url}</td>
                  <td>
                    {provider.has_api_key ? (
                      <span className="badge success">
                        {t('common:llmProviders.apiKeyConfigured')}
                      </span>
                    ) : (
                      <span className="text-muted">—</span>
                    )}
                  </td>
                  <td>
                    {provider.is_active ? (
                      <span className="badge success">{t('common:llmProviders.statusActive')}</span>
                    ) : (
                      <span className="badge rejected">
                        {t('common:llmProviders.statusInactive')}
                      </span>
                    )}
                  </td>
                  <td>
                    {provider.last_test_ok === null ? (
                      <span className="text-muted">
                        {t('common:llmProviders.connectivityUntested')}
                      </span>
                    ) : provider.last_test_ok ? (
                      <span className="text-sm" title={provider.last_test_message || ''}>
                        {t('common:llmProviders.connectivityOk')}
                      </span>
                    ) : (
                      <span
                        className="text-sm"
                        style={{ color: 'var(--color-danger)' }}
                        title={provider.last_test_message || ''}
                      >
                        {t('common:llmProviders.connectivityFail')}
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
                        {actingId === provider.id
                          ? t('common:llmProviders.testing')
                          : t('common:llmProviders.test')}
                      </button>
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => setModelsProvider(provider)}
                      >
                        {t('common:llmProviders.models')}
                      </button>
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => openEditProvider(provider)}
                      >
                        {t('common:llmProviders.edit')}
                      </button>
                      <button
                        type="button"
                        className="danger"
                        onClick={() => setDeleteProviderTarget(provider)}
                        disabled={actingId === provider.id}
                      >
                        {t('common:llmProviders.delete')}
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
        <ModelsModal provider={modelsProvider} onClose={() => setModelsProvider(null)} />
      )}

      <ConfirmDialog
        open={!!deleteProviderTarget}
        title={t('common:llmProviders.confirmDeleteTitle')}
        message={
          deleteProviderTarget ? (
            <>
              {t('common:llmProviders.confirmDeleteMsg', { name: deleteProviderTarget.name })}
              <br />
              <span style={{ color: 'var(--color-text-muted)', fontSize: '0.8125rem' }}>
                {t('common:llmProviders.confirmDeleteNote')}
              </span>
            </>
          ) : null
        }
        confirmText={t('common:llmProviders.confirmDelete')}
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
  const { t } = useTranslation()
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
      title={editing ? t('common:llmProviders.editTitle') : t('common:llmProviders.createTitle')}
      onClose={onClose}
      footer={
        <>
          <button type="button" className="secondary" onClick={onClose}>
            {t('common:llmProviders.cancel')}
          </button>
          <button
            type="button"
            onClick={onSubmit}
            disabled={submitting || !form.name || !form.base_url}
          >
            {submitting ? t('common:llmProviders.saving') : t('common:llmProviders.save')}
          </button>
        </>
      }
    >
      {/* 厂商快捷预设：点击后自动填充表单字段 */}
      <div className="form-group">
        <label>{t('common:llmProviders.presetsLabel')}</label>
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
          {t('common:llmProviders.presetsHint')}
        </p>
      </div>

      <div className="form-group">
        <label htmlFor="provider-name">{t('common:llmProviders.fieldName')}</label>
        <input
          id="provider-name"
          value={form.name}
          onChange={(e) => onFormChange({ ...form, name: e.target.value })}
          placeholder={t('common:llmProviders.fieldNamePlaceholder')}
        />
      </div>
      <div className="form-group">
        <label htmlFor="provider-type">{t('common:llmProviders.fieldType')}</label>
        <select
          id="provider-type"
          value={form.provider_type}
          onChange={(e) =>
            onFormChange({ ...form, provider_type: e.target.value as ProviderType })
          }
        >
          <option value="ollama">{t('common:llmProviders.fieldTypeOllama')}</option>
          <option value="openai">{t('common:llmProviders.fieldTypeOpenAi')}</option>
        </select>
      </div>
      <div className="form-group">
        <label htmlFor="provider-url">{t('common:llmProviders.fieldBaseUrl')}</label>
        <input
          id="provider-url"
          value={form.base_url}
          onChange={(e) => onFormChange({ ...form, base_url: e.target.value })}
          placeholder={t('common:llmProviders.fieldBaseUrlPlaceholder')}
        />
      </div>
      <div className="form-group">
        <label htmlFor="provider-key">
          {t('common:llmProviders.fieldApiKey')}
          {editing && (
            <span className="text-muted text-sm ml-2">
              {t('common:llmProviders.apiKeyHintEdit')}
            </span>
          )}
        </label>
        <input
          id="provider-key"
          type="password"
          value={form.api_key}
          onChange={(e) => onFormChange({ ...form, api_key: e.target.value })}
          placeholder={
            form.provider_type === 'ollama'
              ? t('common:llmProviders.apiKeyPlaceholderOllama')
              : t('common:llmProviders.apiKeyPlaceholderOpenAi')
          }
        />
      </div>
      <div className="form-group">
        <label>
          <input
            type="checkbox"
            checked={form.is_default}
            onChange={(e) => onFormChange({ ...form, is_default: e.target.checked })}
          />{' '}
          {t('common:llmProviders.fieldDefault')}
        </label>
      </div>
      <div className="form-group">
        <label>
          <input
            type="checkbox"
            checked={form.is_active}
            onChange={(e) => onFormChange({ ...form, is_active: e.target.checked })}
          />{' '}
          {t('common:llmProviders.fieldActive')}
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
  const { t } = useTranslation()
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
      setError(getErrorMessage(err, t('common:llmProviders.loadModelsFailed')))
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
        toast.success(t('common:llmProviders.modelToastUpdated'))
      } else {
        const response = await api.post<DataResponse<LlmModel>>(
          `/llm-providers/${provider.id}/models`,
          payload,
        )
        const created = response.data.data
        if (created) {
          setModels((prev) => [...prev, created])
        }
        toast.success(t('common:llmProviders.modelToastCreated'))
      }
      setModelFormOpen(false)
    } catch (err) {
      const msg = getErrorMessage(err, t('common:llmProviders.modelSaveFailed'))
      setError(msg)
      toast.error(t('common:llmProviders.modelSaveFailed'), msg)
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
      toast.success(
        t('common:llmProviders.modelToastDeleted'),
        t('common:llmProviders.modelToastDeletedDesc', { name: model.display_name }),
      )
      setDeleteModelTarget(null)
    } catch (err) {
      const msg = getErrorMessage(err, t('common:llmProviders.modelDeleteFailed'))
      setError(msg)
      toast.error(t('common:llmProviders.modelDeleteFailed'), msg)
    } finally {
      setActingId(null)
    }
  }

  return (
    <Modal
      title={t('common:llmProviders.modelsTitle', { name: provider.name })}
      onClose={onClose}
      footer={
        <button type="button" onClick={onClose}>{t('common:llmProviders.close')}</button>
      }
    >
      {error && <div className="alert alert-error mb-3">{error}</div>}

      <div className="page-header" style={{ marginBottom: '1rem' }}>
        <p className="text-muted text-sm">{t('common:llmProviders.modelsHint')}</p>
        <button type="button" onClick={openCreateModel}>
          {t('common:llmProviders.addModel')}
        </button>
      </div>

      {loading ? (
        <Loading text={t('common:llmProviders.loadingModels')} />
      ) : models.length === 0 ? (
        <EmptyState
          icon="llm"
          title={t('common:llmProviders.modelsEmptyTitle')}
          description={t('common:llmProviders.modelsEmptyDesc')}
        />
      ) : (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>{t('common:llmProviders.colModelName')}</th>
                <th>{t('common:llmProviders.colDisplayName')}</th>
                <th>{t('common:llmProviders.colTier')}</th>
                <th>{t('common:llmProviders.colStatus')}</th>
                <th>{t('common:llmProviders.colActions')}</th>
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
                      <span className="badge success">
                        {t('common:llmProviders.statusActive')}
                      </span>
                    ) : (
                      <span className="badge rejected">
                        {t('common:llmProviders.statusInactive')}
                      </span>
                    )}
                  </td>
                  <td>
                    <div className="action-group">
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => openEditModel(model)}
                      >
                        {t('common:llmProviders.edit')}
                      </button>
                      <button
                        type="button"
                        className="danger"
                        onClick={() => setDeleteModelTarget(model)}
                        disabled={actingId === model.id}
                      >
                        {t('common:llmProviders.delete')}
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
          title={
            editingModel
              ? t('common:llmProviders.editModelTitle')
              : t('common:llmProviders.addModelTitle')
          }
          onClose={() => setModelFormOpen(false)}
          footer={
            <>
              <button type="button" className="secondary" onClick={() => setModelFormOpen(false)}>
                {t('common:llmProviders.cancel')}
              </button>
              <button
                type="button"
                onClick={handleSaveModel}
                disabled={submitting || !modelForm.model_name || !modelForm.display_name}
              >
                {submitting ? t('common:llmProviders.saving') : t('common:llmProviders.save')}
              </button>
            </>
          }
        >
          <div className="form-group">
            <label htmlFor="model-name">{t('common:llmProviders.modelFieldName')}</label>
            <input
              id="model-name"
              value={modelForm.model_name}
              onChange={(e) =>
                onModelFormChange(setModelForm, modelForm, 'model_name', e.target.value)
              }
              placeholder={t('common:llmProviders.modelFieldNamePlaceholder')}
            />
          </div>
          <div className="form-group">
            <label htmlFor="model-display">{t('common:llmProviders.modelFieldDisplayName')}</label>
            <input
              id="model-display"
              value={modelForm.display_name}
              onChange={(e) =>
                onModelFormChange(setModelForm, modelForm, 'display_name', e.target.value)
              }
              placeholder={t('common:llmProviders.modelFieldDisplayNamePlaceholder')}
            />
          </div>
          <div className="form-group">
            <label htmlFor="model-tier">{t('common:llmProviders.modelFieldTier')}</label>
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
              <option value="">{t('common:llmProviders.tierNone')}</option>
              <option value="low">{t('common:llmProviders.tierLow')}</option>
              <option value="medium">{t('common:llmProviders.tierMedium')}</option>
              <option value="high">{t('common:llmProviders.tierHigh')}</option>
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
              {t('common:llmProviders.fieldActive')}
            </label>
          </div>
        </Modal>
      )}

      <ConfirmDialog
        open={!!deleteModelTarget}
        title={t('common:llmProviders.confirmDeleteModelTitle')}
        message={
          deleteModelTarget ? (
            <>
              {t('common:llmProviders.confirmDeleteModelMsg', {
                name: deleteModelTarget.display_name,
              })}
            </>
          ) : null
        }
        confirmText={t('common:llmProviders.confirmDelete')}
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
