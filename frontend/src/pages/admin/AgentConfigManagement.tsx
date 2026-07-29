import { useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import i18n from '../../i18n/config.ts'
import zhCNAgentConfig from '../../i18n/locales/zh-CN/admin-agent-config.json'
import enAgentConfig from '../../i18n/locales/en/admin-agent-config.json'
import EmptyState from '../../components/ui/EmptyState.tsx'
import { ICONS } from '../../components/ui/Icons.tsx'
import { getErrorMessage } from '../../utils/errors.ts'
import {
  listAgentConfigs,
  createAgentConfig,
  updateAgentConfig,
  deleteAgentConfig,
  toggleAgentConfig,
  testAgentConfig,
  duplicateAgentConfig,
  type AgentConfigItem,
  type AgentConfigCreatePayload,
  type AgentConfigUpdatePayload,
  type AgentTestResult,
} from '../../api/agentConfigs.ts'
import { adminApi } from '../../api/adminClient.ts'
import { api } from '../../api/client.ts'

// 独立命名空间 adminAgentConfig 不在 config.ts 的静态资源中（按要求不修改 config.ts），
// 在此模块顶层通过 addResourceBundle 注册，useTranslation 即可解析。
if (!i18n.hasResourceBundle('zh-CN', 'adminAgentConfig')) {
  i18n.addResourceBundle('zh-CN', 'adminAgentConfig', zhCNAgentConfig)
  i18n.addResourceBundle('en', 'adminAgentConfig', enAgentConfig)
}

const TYPE_OPTIONS = ['chat', 'analysis', 'report', 'sql_agent'] as const

const makeFormSchema = (t: TFunction) =>
  z.object({
    name: z.string().min(1, t('form.validation.required')),
    description: z.string().optional(),
    agent_type: z.string().min(1, t('form.validation.required')),
    model_id: z.string().optional(),
    prompt_id: z.string().optional(),
    system_prompt: z.string().optional(),
    max_iterations: z.number().min(1).max(100).default(10),
    temperature: z.number().min(0).max(2).default(0.7),
    tool_ids: z.array(z.string()).default([]),
    skill_ids: z.array(z.string()).default([]),
  })

type FormValues = z.infer<ReturnType<typeof makeFormSchema>>

interface SelectOption {
  id: string
  name?: string
  model_name?: string
  display_name?: string
  label?: string
}

export default function AgentConfigManagement() {
  const { t } = useTranslation('adminAgentConfig')
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [formOpen, setFormOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [testOpen, setTestOpen] = useState(false)
  const [testTarget, setTestTarget] = useState<AgentConfigItem | null>(null)
  const [testMessage, setTestMessage] = useState(t('test.defaultMessage'))
  const [testResult, setTestResult] = useState<AgentTestResult | null>(null)
  const [testLoading, setTestLoading] = useState(false)
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null)

  const formSchema = useMemo(() => makeFormSchema(t), [t])

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema) as any,
    defaultValues: {
      name: '',
      description: '',
      agent_type: 'chat',
      model_id: '',
      prompt_id: '',
      system_prompt: '',
      max_iterations: 10,
      temperature: 0.7,
      tool_ids: [],
      skill_ids: [],
    },
  })

  const { data: listData, isLoading, isError, refetch } = useQuery({
    queryKey: ['agentConfigs', page, search, typeFilter, statusFilter],
    queryFn: async () => {
      const res = await listAgentConfigs({
        page,
        page_size: 20,
        search: search || undefined,
        agent_type: typeFilter || undefined,
        is_active: statusFilter || undefined,
      })
      return res.data.data
    },
  })

  const { data: modelsData } = useQuery({
    queryKey: ['modelConfigsForAgent'],
    queryFn: async () => {
      const res = await adminApi.get('/model-configs', { params: { page_size: 100 } })
      return (res.data?.data?.items ?? []) as SelectOption[]
    },
    staleTime: 60000,
  })

  const { data: promptsData } = useQuery({
    queryKey: ['promptsForAgent'],
    queryFn: async () => {
      const res = await api.get('/prompts', { params: { page_size: 100 } })
      return (res.data?.data?.items ?? []) as SelectOption[]
    },
    staleTime: 60000,
  })

  const { data: toolsData } = useQuery({
    queryKey: ['toolsForAgent'],
    queryFn: async () => {
      const res = await adminApi.get('/tools', { params: { page_size: 100 } })
      return (res.data?.data?.items ?? []) as SelectOption[]
    },
    staleTime: 60000,
  })

  const { data: skillsData } = useQuery({
    queryKey: ['skillsForAgent'],
    queryFn: async () => {
      const res = await adminApi.get('/skills', { params: { page_size: 100 } })
      return (res.data?.data?.items ?? []) as SelectOption[]
    },
    staleTime: 60000,
  })

  const createMut = useMutation({
    mutationFn: (payload: AgentConfigCreatePayload) => createAgentConfig(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agentConfigs'] })
      setFormOpen(false)
      setEditingId(null)
      form.reset()
    },
  })

  const updateMut = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: AgentConfigUpdatePayload }) =>
      updateAgentConfig(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agentConfigs'] })
      setFormOpen(false)
      setEditingId(null)
      form.reset()
    },
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteAgentConfig(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agentConfigs'] })
      setDeleteConfirmId(null)
    },
  })

  const toggleMut = useMutation({
    mutationFn: (id: string) => toggleAgentConfig(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['agentConfigs'] }),
  })

  const duplicateMut = useMutation({
    mutationFn: (id: string) => duplicateAgentConfig(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['agentConfigs'] }),
  })

  function openCreate() {
    setEditingId(null)
    form.reset({
      name: '',
      description: '',
      agent_type: 'chat',
      model_id: '',
      prompt_id: '',
      system_prompt: '',
      max_iterations: 10,
      temperature: 0.7,
      tool_ids: [],
      skill_ids: [],
    })
    setFormOpen(true)
  }

  function openEdit(item: AgentConfigItem) {
    setEditingId(item.id)
    form.reset({
      name: item.name,
      description: item.description ?? '',
      agent_type: item.agent_type,
      model_id: item.model_id ?? '',
      prompt_id: item.prompt_id ?? '',
      system_prompt: item.system_prompt ?? '',
      max_iterations: item.max_iterations,
      temperature: item.temperature,
      tool_ids: item.tool_ids ?? [],
      skill_ids: item.skill_ids ?? [],
    })
    setFormOpen(true)
  }

  function onSubmit(values: FormValues) {
    const payload: AgentConfigCreatePayload = {
      name: values.name,
      description: values.description || undefined,
      agent_type: values.agent_type,
      model_id: values.model_id || undefined,
      prompt_id: values.prompt_id || undefined,
      system_prompt: values.system_prompt || undefined,
      max_iterations: values.max_iterations,
      temperature: values.temperature,
      tool_ids: values.tool_ids,
      skill_ids: values.skill_ids,
    }
    if (editingId) {
      updateMut.mutate({ id: editingId, payload })
    } else {
      createMut.mutate(payload)
    }
  }

  async function handleTest() {
    if (!testTarget) return
    setTestLoading(true)
    setTestResult(null)
    try {
      const res = await testAgentConfig(testTarget.id, { message: testMessage })
      setTestResult(res.data.data)
    } catch (e) {
      setTestResult({
        success: false,
        message: getErrorMessage(e),
        thinking: null,
        answer: null,
        execution_time_ms: 0,
      })
    } finally {
      setTestLoading(false)
    }
  }

  const isMutating = createMut.isPending || updateMut.isPending
  const mutationError = createMut.error || updateMut.error
  const tableHeaders = [
    'table.name',
    'table.type',
    'table.model',
    'table.prompt',
    'table.tools',
    'table.skills',
    'table.status',
    'table.actions',
  ] as const

  return (
    <div style={{ padding: 24 }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0 }}>{t('title')}</h1>
        <button onClick={openCreate} style={btnPrimaryStyle}>
          {'+ '}{t('toolbar.create')}
        </button>
      </div>

      {/* Filters */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
        <input
          placeholder={t('filters.searchPlaceholder')}
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1) }}
          style={inputStyle}
        />
        <select value={typeFilter} onChange={(e) => { setTypeFilter(e.target.value); setPage(1) }} style={selectStyle}>
          <option value="">{t('filters.allTypes')}</option>
          {TYPE_OPTIONS.map((v) => (
            <option key={v} value={v}>{t(`types.${v}`)}</option>
          ))}
        </select>
        <select value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); setPage(1) }} style={selectStyle}>
          <option value="">{t('filters.allStatuses')}</option>
          <option value="active">{t('statuses.active')}</option>
          <option value="inactive">{t('statuses.inactive')}</option>
        </select>
      </div>

      {/* Table */}
      <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #e5e7eb', overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ background: '#f9fafb', borderBottom: '1px solid #e5e7eb' }}>
              {tableHeaders.map((h) => (
                <th key={h} style={{ padding: '10px 12px', textAlign: 'left', fontSize: 13, color: '#6b7280', fontWeight: 600 }}>
                  {t(h)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={8} style={{ textAlign: 'center', padding: 40 }}>{t('status.loading')}</td>
              </tr>
            ) : isError ? (
              <tr>
                <td colSpan={8} style={{ textAlign: 'center', padding: 40 }}>
                  <EmptyState
                    title={t('messages.loadFailed')}
                    size="sm"
                    action={
                      <button onClick={() => refetch()} style={btnSmallStyle}>
                        {t('actions.retry')}
                      </button>
                    }
                  />
                </td>
              </tr>
            ) : listData?.items.length === 0 ? (
              <tr>
                <td colSpan={8} style={{ textAlign: 'center', padding: 40 }}>
                  <EmptyState title={t('empty.noConfigs')} size="sm" />
                </td>
              </tr>
            ) : (
              listData?.items.map((item) => (
                <tr key={item.id} style={{ borderBottom: '1px solid #f3f4f6' }}>
                  <td style={{ padding: '10px 12px', fontWeight: 500 }}>{item.name}</td>
                  <td style={{ padding: '10px 12px' }}>
                    <span style={{
                      display: 'inline-block',
                      padding: '2px 8px',
                      borderRadius: 6,
                      fontSize: 12,
                      border: '1px solid',
                      ...badgeColorStyle(item.agent_type),
                    }}>
                      {t(`types.${item.agent_type}`, { defaultValue: item.agent_type })}
                    </span>
                  </td>
                  <td style={{ padding: '10px 12px', fontSize: 13, color: '#6b7280' }}>
                    {modelsData?.find((m) => m.id === item.model_id)?.model_name || modelsData?.find((m) => m.id === item.model_id)?.name || '—'}
                  </td>
                  <td style={{ padding: '10px 12px', fontSize: 13, color: '#6b7280' }}>
                    {promptsData?.find((p) => p.id === item.prompt_id)?.name || '—'}
                  </td>
                  <td style={{ padding: '10px 12px', fontSize: 13 }}>{(item.tool_ids?.length ?? 0)}</td>
                  <td style={{ padding: '10px 12px', fontSize: 13 }}>{(item.skill_ids?.length ?? 0)}</td>
                  <td style={{ padding: '10px 12px' }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                      <input
                        type="checkbox"
                        checked={item.is_active}
                        onChange={() => toggleMut.mutate(item.id)}
                        style={{ width: 16, height: 16, accentColor: '#3b82f6' }}
                      />
                      <span style={{ fontSize: 12, color: item.is_active ? '#22c55e' : '#9ca3af' }}>
                        {item.is_active ? t('status.active') : t('status.inactive')}
                      </span>
                    </label>
                  </td>
                  <td style={{ padding: '10px 12px' }}>
                    <div style={{ display: 'flex', gap: 4 }}>
                      <button onClick={() => { setTestTarget(item); setTestOpen(true); setTestResult(null) }} style={btnSmallStyle} title={t('actions.test')}>
                        <ICONS.send size={14} />
                      </button>
                      <button onClick={() => duplicateMut.mutate(item.id)} style={btnSmallStyle} title={t('actions.duplicate')}>
                        <ICONS.copy size={14} />
                      </button>
                      <button onClick={() => openEdit(item)} style={btnSmallStyle} title={t('actions.edit')}>
                        <ICONS.reports size={14} />
                      </button>
                      <button onClick={() => setDeleteConfirmId(item.id)} style={{ ...btnSmallStyle, color: '#ef4444' }} title={t('actions.delete')}>
                        <ICONS.close size={14} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>

        {/* Pagination */}
        {listData && listData.total > 20 && (
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 16px', borderTop: '1px solid #e5e7eb' }}>
            <span style={{ fontSize: 13, color: '#6b7280' }}>{t('pagination.info', { total: listData.total })}</span>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                style={{ ...btnSmallStyle, opacity: page <= 1 ? 0.5 : 1 }}
              >
                {t('pagination.prev')}
              </button>
              <span style={{ fontSize: 13, padding: '4px 8px' }}>{t('pagination.currentPage', { page })}</span>
              <button
                onClick={() => setPage((p) => p + 1)}
                disabled={page * 20 >= listData.total}
                style={{ ...btnSmallStyle, opacity: page * 20 >= listData.total ? 0.5 : 1 }}
              >
                {t('pagination.next')}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Create/Edit Dialog */}
      {formOpen && (
        <div style={overlayStyle} onClick={() => { setFormOpen(false); setEditingId(null) }}>
          <div style={dialogWideStyle} onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <h2 style={{ fontSize: 18, fontWeight: 600, margin: 0 }}>
                {editingId ? t('form.editTitle') : t('form.createTitle')}
              </h2>
              <button onClick={() => { setFormOpen(false); setEditingId(null) }} style={btnSmallStyle}>
                <ICONS.close size={18} />
              </button>
            </div>

            <form onSubmit={form.handleSubmit(onSubmit)}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                <div>
                  <label style={labelStyle}>{t('form.name')} *</label>
                  <input {...form.register('name')} style={inputStyle} placeholder={t('form.namePlaceholder')} />
                  {form.formState.errors.name && <p style={errorStyle}>{form.formState.errors.name.message}</p>}
                </div>
                <div>
                  <label style={labelStyle}>{t('form.type')} *</label>
                  <select {...form.register('agent_type')} style={selectStyle}>
                    {TYPE_OPTIONS.map((v) => (
                      <option key={v} value={v}>{t(`form.typeOptions.${v}`)}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label style={labelStyle}>{t('form.description')}</label>
                  <input {...form.register('description')} style={inputStyle} placeholder={t('form.descriptionPlaceholder')} />
                </div>
                <div>
                  <label style={labelStyle}>{t('form.model')}</label>
                  <select {...form.register('model_id')} style={selectStyle}>
                    <option value="">{t('form.notLinked')}</option>
                    {(modelsData ?? []).map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.model_name || m.name || m.id}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label style={labelStyle}>{t('form.promptTemplate')}</label>
                  <select {...form.register('prompt_id')} style={selectStyle}>
                    <option value="">{t('form.notLinked')}</option>
                    {(promptsData ?? []).map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name || p.id}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label style={labelStyle}>{t('form.maxIterations')}</label>
                  <input
                    type="number"
                    {...form.register('max_iterations', { valueAsNumber: true })}
                    style={inputStyle}
                    min={1}
                    max={100}
                  />
                </div>
              </div>

              <div style={{ marginTop: 16 }}>
                <label style={labelStyle}>
                  {t('form.temperature')}: {form.watch('temperature').toFixed(1)}
                </label>
                <input
                  type="range"
                  min="0"
                  max="2"
                  step="0.1"
                  {...form.register('temperature', { valueAsNumber: true })}
                  style={{ width: '100%' }}
                />
              </div>

              <div style={{ marginTop: 16 }}>
                <label style={labelStyle}>{t('form.systemPrompt')}</label>
                <textarea
                  {...form.register('system_prompt')}
                  style={{ ...inputStyle, minHeight: 120, fontFamily: 'monospace', fontSize: 13 }}
                  placeholder={t('form.systemPromptPlaceholder')}
                  rows={6}
                />
              </div>

              {/* Tool select multi */}
              <div style={{ marginTop: 16 }}>
                <label style={labelStyle}>{t('form.tools')}</label>
                <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
                  <select
                    multiple
                    value={form.watch('tool_ids')}
                    onChange={(e) => {
                      const selected = Array.from(e.target.selectedOptions, (o) => o.value)
                      form.setValue('tool_ids', selected)
                    }}
                    style={{ ...selectStyle, height: 140, width: '100%' }}
                  >
                    {(toolsData ?? []).map((tool) => (
                      <option key={tool.id} value={tool.id}>
                        {tool.display_name || tool.name || tool.id}
                      </option>
                    ))}
                  </select>
                </div>
                <p style={{ fontSize: 12, color: '#9ca3af', marginTop: 4 }}>
                  {t('form.multiSelectHint')}
                </p>
              </div>

              {/* Skill select multi */}
              <div style={{ marginTop: 16 }}>
                <label style={labelStyle}>{t('form.skills')}</label>
                <select
                  multiple
                  value={form.watch('skill_ids')}
                  onChange={(e) => {
                    const selected = Array.from(e.target.selectedOptions, (o) => o.value)
                    form.setValue('skill_ids', selected)
                  }}
                  style={{ ...selectStyle, height: 140, width: '100%' }}
                >
                  {(skillsData ?? []).map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.display_name || s.name || s.id}
                    </option>
                  ))}
                </select>
                <p style={{ fontSize: 12, color: '#9ca3af', marginTop: 4 }}>
                  {t('form.multiSelectHint')}
                </p>
              </div>

              {/* Error */}
              {mutationError && (
                <p style={errorStyle}>
                  {getErrorMessage(mutationError)}
                </p>
              )}

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 24 }}>
                <button
                  type="button"
                  onClick={() => { setFormOpen(false); setEditingId(null) }}
                  style={btnSecondaryStyle}
                >
                  {t('form.cancel')}
                </button>
                <button type="submit" disabled={isMutating} style={btnPrimaryStyle}>
                  {isMutating ? t('form.saving') : editingId ? t('form.save') : t('form.create')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Test Dialog */}
      {testOpen && testTarget && (
        <TestDialog
          target={testTarget}
          message={testMessage}
          onMessageChange={setTestMessage}
          result={testResult}
          loading={testLoading}
          onTest={handleTest}
          onClose={() => setTestOpen(false)}
        />
      )}

      {/* Delete Confirm */}
      {deleteConfirmId && (
        <DeleteConfirmDialog
          deleting={deleteMut.isPending}
          errorText={deleteMut.error ? getErrorMessage(deleteMut.error) : null}
          onCancel={() => setDeleteConfirmId(null)}
          onConfirm={() => deleteMut.mutate(deleteConfirmId)}
        />
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Test Dialog                                                        */
/* ------------------------------------------------------------------ */

function TestDialog({
  target,
  message,
  onMessageChange,
  result,
  loading,
  onTest,
  onClose,
}: {
  target: AgentConfigItem
  message: string
  onMessageChange: (v: string) => void
  result: AgentTestResult | null
  loading: boolean
  onTest: () => void
  onClose: () => void
}) {
  const { t } = useTranslation('adminAgentConfig')
  return (
    <div style={overlayStyle} onClick={onClose}>
      <div style={dialogStyle} onClick={(e) => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h2 style={{ fontSize: 18, fontWeight: 600, margin: 0 }}>{t('test.title', { name: target.name })}</h2>
          <button onClick={onClose} style={btnSmallStyle}><ICONS.close size={18} /></button>
        </div>

        <label style={labelStyle}>{t('test.messageLabel')}</label>
        <input
          value={message}
          onChange={(e) => onMessageChange(e.target.value)}
          style={inputStyle}
          placeholder={t('test.messagePlaceholder')}
        />

        <button
          onClick={onTest}
          disabled={loading}
          style={{ ...btnPrimaryStyle, marginTop: 12 }}
        >
          {loading ? t('test.testing') : t('test.send')}
        </button>

        {result && (
          <div style={{
            marginTop: 16,
            padding: 12,
            borderRadius: 8,
            background: result.success ? '#f0fdf4' : '#fef2f2',
            border: `1px solid ${result.success ? '#bbf7d0' : '#fecaca'}`,
          }}>
            <p style={{ fontSize: 13, fontWeight: 600, color: result.success ? '#166534' : '#991b1b' }}>
              {result.message}
            </p>
            {result.thinking && (
              <div style={{ marginTop: 8, fontSize: 12, color: '#6b7280' }}>
                <strong>{t('test.thinking')}:</strong> {result.thinking}
              </div>
            )}
            {result.answer && (
              <div style={{ marginTop: 8, fontSize: 13, whiteSpace: 'pre-wrap' }}>
                <strong>{t('test.answer')}:</strong> {result.answer}
              </div>
            )}
            {result.execution_time_ms > 0 && (
              <div style={{ marginTop: 8, fontSize: 12, color: '#9ca3af' }}>
                {t('test.duration', { ms: result.execution_time_ms })}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Delete Confirm Dialog                                              */
/* ------------------------------------------------------------------ */

function DeleteConfirmDialog({
  deleting,
  errorText,
  onCancel,
  onConfirm,
}: {
  deleting: boolean
  errorText: string | null
  onCancel: () => void
  onConfirm: () => void
}) {
  const { t } = useTranslation('adminAgentConfig')
  return (
    <div style={overlayStyle} onClick={onCancel}>
      <div style={dialogStyle} onClick={(e) => e.stopPropagation()}>
        <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 12 }}>{t('delete.title')}</h2>
        <p style={{ color: '#6b7280', marginBottom: 20 }}>{t('delete.message')}</p>
        {errorText && (
          <p style={errorStyle}>{errorText}</p>
        )}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button onClick={onCancel} style={btnSecondaryStyle}>{t('delete.cancel')}</button>
          <button
            onClick={onConfirm}
            disabled={deleting}
            style={{ ...btnPrimaryStyle, background: '#ef4444' }}
          >
            {deleting ? t('delete.deleting') : t('delete.confirm')}
          </button>
        </div>
      </div>
    </div>
  )
}

// Styles
const overlayStyle: React.CSSProperties = {
  position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  zIndex: 1000,
}

const dialogStyle: React.CSSProperties = {
  background: '#fff', borderRadius: 12, padding: 24,
  minWidth: 420, maxWidth: 520, width: '100%',
  boxShadow: '0 20px 60px rgba(0,0,0,.3)',
}

const dialogWideStyle: React.CSSProperties = {
  background: '#fff', borderRadius: 12, padding: 24,
  minWidth: 600, maxWidth: 900, width: '100%', maxHeight: '90vh', overflow: 'auto',
  boxShadow: '0 20px 60px rgba(0,0,0,.3)',
}

const inputStyle: React.CSSProperties = {
  width: '100%', padding: '8px 12px', border: '1px solid #d1d5db',
  borderRadius: 6, fontSize: 14, boxSizing: 'border-box',
}

const selectStyle: React.CSSProperties = {
  width: '100%', padding: '8px 12px', border: '1px solid #d1d5db',
  borderRadius: 6, fontSize: 14, background: '#fff', boxSizing: 'border-box',
}

const labelStyle: React.CSSProperties = {
  display: 'block', fontSize: 13, fontWeight: 500, color: '#374151', marginBottom: 4,
}

const errorStyle: React.CSSProperties = {
  color: '#ef4444', fontSize: 13, marginTop: 4,
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
  background: '#fff', cursor: 'pointer', display: 'inline-flex', alignItems: 'center',
  fontSize: 13,
}

function badgeColorStyle(agentType: string): React.CSSProperties {
  const colorMap: Record<string, { bg: string; color: string; border: string }> = {
    chat: { bg: '#dbeafe', color: '#1e40af', border: '#93c5fd' },
    analysis: { bg: '#dcfce7', color: '#166534', border: '#86efac' },
    report: { bg: '#f3e8ff', color: '#6b21a8', border: '#c4b5fd' },
    sql_agent: { bg: '#fef3c7', color: '#92400e', border: '#fcd34d' },
  }
  const c = colorMap[agentType] ?? { bg: '#f3f4f6', color: '#374151', border: '#d1d5db' }
  return { background: c.bg, color: c.color, borderColor: c.border }
}
