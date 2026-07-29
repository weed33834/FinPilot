import { useEffect, useMemo, useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import i18n from '../../i18n/config.ts'
import zhCNAdminModel from '../../i18n/locales/zh-CN/admin-model.json'
import enAdminModel from '../../i18n/locales/en/admin-model.json'
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

// adminModel 命名空间按需注册（config.ts 不在本页改动范围内）
i18n.addResourceBundle('zh-CN', 'adminModel', zhCNAdminModel)
i18n.addResourceBundle('en', 'adminModel', enAdminModel)

// --------------- Constants ---------------

const PROVIDERS = [
  { value: 'openai', apiBase: 'https://api.openai.com/v1' },
  { value: 'anthropic', apiBase: 'https://api.anthropic.com' },
  { value: 'google', apiBase: 'https://generativelanguage.googleapis.com/v1beta' },
  { value: 'local', apiBase: 'http://localhost:8080/v1' },
  { value: 'ollama', apiBase: 'http://localhost:11434/v1' },
  { value: 'lmstudio', apiBase: 'http://localhost:1234/v1' },
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

const makeModelFormSchema = (t: TFunction) =>
  z.object({
    provider: z.string().min(1, t('form.validation.providerRequired')),
    model_name: z.string().min(1, t('form.validation.modelNameRequired')),
    display_name: z.string().min(1, t('form.validation.displayNameRequired')),
    api_base: z.string().min(1, t('form.validation.apiBaseRequired')),
    api_key: z.string().optional(),
    is_default: z.boolean().default(false),
    is_active: z.boolean().default(true),
    temperature: z.coerce.number().min(0).max(2).default(0.7),
    max_tokens: z.coerce.number().min(1).max(128000).default(4096),
    top_p: z.coerce.number().min(0).max(1).default(0.9),
  })

type ModelFormValues = z.infer<ReturnType<typeof makeModelFormSchema>>

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
  const { t } = useTranslation('adminModel')
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

  const modelFormSchema = useMemo(() => makeModelFormSchema(t), [t])

  const form = useForm<ModelFormData>({
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    resolver: zodResolver(modelFormSchema) as any,
    defaultValues: EMPTY_FORM,
  })

  const providerLabel = (value: string) => t(`providers.${value}`, { defaultValue: value })

  // Query
  const { data, isLoading, isError, error, refetch } = useQuery({
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
      setTestResult({ success: false, message: getErrorMessage(err, t('messages.testFailed')), result: null })
    } finally {
      setTesting(false)
    }
  }

  const submitLabel = editingId ? t('actions.save') : t('actions.create')
  const mutError =
    createMut.error || updateMut.error
      ? getErrorMessage(createMut.error || updateMut.error, t('messages.operationFailed'))
      : ''

  // Reset page on filter change
  useEffect(() => {
    setPage(1)
  }, [search, providerFilter, statusFilter])

  return (
    <div className="admin-model-management">
      {/* Header */}
      <div className="admin-page-header">
        <h1 className="admin-page-title">{t('title')}</h1>
        <p className="admin-page-desc">{t('description')}</p>
      </div>

      {/* Toolbar */}
      <div className="admin-toolbar">
        <div className="admin-toolbar-left">
          <div className="admin-search-box">
            <ICONS.search size={14} />
            <input
              type="text"
              placeholder={t('search.placeholder')}
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
            <option value="">{t('filters.allProviders')}</option>
            {PROVIDERS.map((p) => (
              <option key={p.value} value={p.value}>
                {providerLabel(p.value)}
              </option>
            ))}
          </select>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="admin-filter-select"
          >
            <option value="">{t('filters.allStatus')}</option>
            <option value="active">{t('filters.status.active')}</option>
            <option value="inactive">{t('filters.status.inactive')}</option>
          </select>
        </div>
        <div className="admin-toolbar-right">
          <button className="btn btn-primary" onClick={openCreate}>
            <ICONS.dashboard size={14} /> {t('actions.add')}
          </button>
        </div>
      </div>

      {/* Content */}
      {isLoading ? (
        <Loading />
      ) : isError ? (
        <div
          className="admin-error"
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 12,
          }}
        >
          <span>{getErrorMessage(error, t('messages.loadFailed'))}</span>
          <button className="admin-action-btn" onClick={() => void refetch()}>
            <ICONS.refresh size={14} /> {t('actions.retry')}
          </button>
        </div>
      ) : items.length === 0 ? (
        <EmptyState title={t('empty.noModels')} />
      ) : (
        <>
          <div className="admin-table-wrapper">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>{t('table.displayName')}</th>
                  <th>{t('table.provider')}</th>
                  <th>{t('table.modelName')}</th>
                  <th>{t('table.apiBase')}</th>
                  <th style={{ width: 70, textAlign: 'center' }}>{t('table.default')}</th>
                  <th style={{ width: 80, textAlign: 'center' }}>{t('table.status')}</th>
                  <th style={{ width: 180, textAlign: 'right' }}>{t('table.actions')}</th>
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
                        {providerLabel(item.provider)}
                      </span>
                    </td>
                    <td className="admin-table-mono">{item.model_name}</td>
                    <td className="admin-table-mono" style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {item.api_base}
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      {item.is_default ? (
                        <span title={t('status.defaultModel')} style={{ color: '#f59e0b', fontSize: 18 }}>
                          ★
                        </span>
                      ) : (
                        <button
                          className="admin-icon-btn"
                          title={t('actions.setAsDefault')}
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
                        title={item.is_active ? t('status.activeToggleOn') : t('status.activeToggleOff')}
                      >
                        <span className="admin-toggle-knob" />
                      </button>
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <div className="admin-actions">
                        <button
                          className="admin-action-btn"
                          title={t('actions.testConnection')}
                          onClick={() => handleTest(item)}
                        >
                          <ICONS.send size={14} />
                        </button>
                        <button
                          className="admin-action-btn"
                          title={t('actions.edit')}
                          onClick={() => openEdit(item)}
                        >
                          <ICONS.settings size={14} />
                        </button>
                        <button
                          className="admin-action-btn danger"
                          title={t('actions.delete')}
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
                {t('pagination.prev')}
              </button>
              <span>{t('pagination.info', { page, totalPages, total })}</span>
              <button disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
                {t('pagination.next')}
              </button>
            </div>
          )}
        </>
      )}

      {/* Create/Edit Dialog */}
      {formOpen && (
        <Modal
          title={editingId ? t('form.editTitle') : t('form.createTitle')}
          onClose={() => setFormOpen(false)}
          footer={
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button className="btn btn-secondary" onClick={() => setFormOpen(false)}>
                {t('actions.cancel')}
              </button>
              <button
                className="btn btn-primary"
                onClick={form.handleSubmit(onSubmit)}
                disabled={createMut.isPending || updateMut.isPending}
              >
                {createMut.isPending || updateMut.isPending ? t('actions.saving') : submitLabel}
              </button>
            </div>
          }
        >
          <form className="admin-form" onSubmit={form.handleSubmit(onSubmit)}>
            {mutError && <div className="admin-form-error">{mutError}</div>}

            <div className="admin-form-row">
              <label className="admin-form-label">{t('form.provider')}</label>
              <select
                className="admin-form-select"
                {...form.register('provider')}
                onChange={(e) => handleProviderChange(e.target.value)}
              >
                {PROVIDERS.map((p) => (
                  <option key={p.value} value={p.value}>
                    {providerLabel(p.value)}
                  </option>
                ))}
              </select>
            </div>

            <div className="admin-form-row">
              <label className="admin-form-label">{t('form.displayName')}</label>
              <input className="admin-form-input" {...form.register('display_name')} placeholder={t('form.displayNamePlaceholder')} />
            </div>

            <div className="admin-form-row">
              <label className="admin-form-label">{t('form.modelName')}</label>
              <input className="admin-form-input" {...form.register('model_name')} placeholder={t('form.modelNamePlaceholder')} />
            </div>

            <div className="admin-form-row">
              <label className="admin-form-label">{t('form.apiBase')}</label>
              <input className="admin-form-input" {...form.register('api_base')} placeholder={t('form.apiBasePlaceholder')} />
            </div>

            <div className="admin-form-row">
              <label className="admin-form-label">
                {t('form.apiKey')} {editingId && <span className="admin-form-hint">{t('form.apiKeyKeepHint')}</span>}
              </label>
              <input
                className="admin-form-input"
                type="password"
                {...form.register('api_key')}
                placeholder={editingId ? t('form.apiKeyKeepPlaceholder') : t('form.apiKeyPlaceholder')}
              />
            </div>

            <div className="admin-form-row">
              <label className="admin-form-label">{t('form.parameters')}</label>
              <div className="admin-form-inline">
                <div className="admin-form-field">
                  <span>{t('form.temperature')}</span>
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
                  <span>{t('form.maxTokens')}</span>
                  <input
                    type="number"
                    min="1"
                    max="128000"
                    className="admin-form-input-sm"
                    {...form.register('max_tokens')}
                  />
                </div>
                <div className="admin-form-field">
                  <span>{t('form.topP')}</span>
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
                <span>{t('form.setAsDefault')}</span>
              </label>
            </div>
          </form>
        </Modal>
      )}

      {/* Test Connection Dialog */}
      {testOpen && testTarget && (
        <Modal title={t('test.title', { name: testTarget.display_name })} onClose={() => setTestOpen(false)}>
          <div className="admin-test-body">
            <div className="admin-test-info">
              <span className="admin-test-label">{t('test.providerLabel')}</span>
              {providerLabel(testTarget.provider)}
            </div>
            <div className="admin-test-info">
              <span className="admin-test-label">{t('test.modelLabel')}</span>
              {testTarget.model_name}
            </div>

            {testing ? (
              <div className="admin-test-loading">
                <Loading />
                <span>{t('test.testing')}</span>
              </div>
            ) : testResult ? (
              <div className={`admin-test-result ${testResult.success ? 'success' : 'error'}`}>
                <div className="admin-test-result-header">
                  {testResult.success ? (
                    <>
                      <ICONS.check size={18} />
                      <span style={{ color: '#16a34a' }}>{t('test.success')}</span>
                    </>
                  ) : (
                    <>
                      <ICONS.close size={18} />
                      <span style={{ color: '#dc2626' }}>{t('test.failed')}</span>
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
        <Modal title={t('confirm.deleteTitle')} onClose={() => setDeleteConfirm(null)}>
          <p style={{ marginBottom: 16 }}>{t('confirm.deleteMessage')}</p>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button className="btn btn-secondary" onClick={() => setDeleteConfirm(null)}>
              {t('actions.cancel')}
            </button>
            <button
              className="btn btn-danger"
              onClick={() => deleteMut.mutate(deleteConfirm)}
              disabled={deleteMut.isPending}
            >
              {deleteMut.isPending ? t('actions.deleting') : t('actions.confirmDelete')}
            </button>
          </div>
          {deleteMut.error && (
            <div className="admin-form-error" style={{ marginTop: 8 }}>
              {getErrorMessage(deleteMut.error, t('messages.deleteFailed'))}
            </div>
          )}
        </Modal>
      )}
    </div>
  )
}
