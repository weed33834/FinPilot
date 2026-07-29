import { useEffect, useMemo, useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import Modal from '../../components/ui/Modal.tsx'
import Loading from '../../components/ui/Loading.tsx'
import EmptyState from '../../components/ui/EmptyState.tsx'
import { ICONS } from '../../components/ui/Icons.tsx'
import { getErrorMessage } from '../../utils/errors.ts'
import { formatDateTime } from '../../utils/format.ts'
import {
  listPrompts,
  createPrompt,
  updatePrompt,
  deletePrompt,
  togglePrompt,
  duplicatePrompt,
  renderPrompt,
  getPromptCategories,
  aiGeneratePrompt,
  exportPrompts,
  importPrompts,
  type PromptTemplateItem,
  type PromptCreatePayload,
  type PromptExportItem,
} from '../../api/prompts.ts'

// --------------- Constants ---------------

const CATEGORY_COLORS: Record<string, string> = {
  chat: '#3b82f6',
  analysis: '#8b5cf6',
  report: '#10b981',
  sql_generation: '#f59e0b',
  audit: '#ef4444',
  general: '#6b7280',
  custom: '#ec4899',
  query: '#06b6d4',
  default: '#6b7280',
}

// --------------- Form Schema ---------------

const makePromptFormSchema = (t: TFunction) =>
  z.object({
    name: z.string().min(1, t('form.validation.nameRequired')),
    description: z.string().optional(),
    template_type: z.string().min(1, t('form.validation.categoryRequired')),
    content: z.string().min(1, t('form.validation.contentRequired')),
    user_template: z.string().optional(),
    variables: z.array(z.string()).default([]),
  })

type PromptFormValues = z.infer<ReturnType<typeof makePromptFormSchema>>

interface PromptFormData {
  name: string
  description?: string
  template_type: string
  content: string
  user_template?: string
  variables: string[]
}

const EMPTY_FORM: PromptFormData = {
  name: '',
  description: '',
  template_type: 'general',
  content: '',
  user_template: '',
  variables: [],
}

// --------------- Component ---------------

export default function PromptManagement() {
  const { t } = useTranslation('adminPrompt')
  const queryClient = useQueryClient()

  const [search, setSearch] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [page, setPage] = useState(1)

  const [formOpen, setFormOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null)

  // Render test state
  const [renderOpen, setRenderOpen] = useState(false)
  const [renderTarget, setRenderTarget] = useState<PromptTemplateItem | null>(null)
  const [renderVars, setRenderVars] = useState<Record<string, string>>({})
  const [renderResult, setRenderResult] = useState<string | null>(null)
  const [rendering, setRendering] = useState(false)

  // Tag input state
  const [tagInput, setTagInput] = useState('')

  // AI 自动生成提示词状态
  const [aiOpen, setAiOpen] = useState(false)
  const [aiDescription, setAiDescription] = useState('')
  const [aiCategory, setAiCategory] = useState('general')
  const [aiTone, setAiTone] = useState<'professional' | 'concise' | 'friendly'>('professional')
  const [aiLanguage, setAiLanguage] = useState<'zh' | 'en'>('zh')
  const [aiGenerating, setAiGenerating] = useState(false)
  const [aiResult, setAiResult] = useState<{
    name: string
    description: string
    content: string
    variables: string[]
  } | null>(null)
  const [aiError, setAiError] = useState('')
  const [importBusy, setImportBusy] = useState(false)
  const [importMessage, setImportMessage] = useState('')
  const [importSuccess, setImportSuccess] = useState(false)

  const promptFormSchema = useMemo(() => makePromptFormSchema(t), [t])

  const form = useForm<PromptFormData>({
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    resolver: zodResolver(promptFormSchema) as any,
    defaultValues: EMPTY_FORM,
  })

  const variables = form.watch('variables')

  // Queries
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['prompts', search, categoryFilter, statusFilter, page],
    queryFn: () =>
      listPrompts({
        page,
        page_size: 20,
        search,
        template_type: categoryFilter,
        is_active: statusFilter,
      }).then((r) => r.data),
  })

  const items = data?.data?.items ?? []
  const total = data?.data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / 20))

  const { data: categoriesData } = useQuery({
    queryKey: ['prompt-categories'],
    queryFn: () => getPromptCategories().then((r) => r.data),
  })
  const categories = categoriesData?.data ?? []

  // Mutations
  const createMut = useMutation({
    mutationFn: (payload: PromptCreatePayload) => createPrompt(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['prompts'] })
      queryClient.invalidateQueries({ queryKey: ['prompt-categories'] })
      setFormOpen(false)
    },
  })

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: string; data: PromptCreatePayload }) =>
      updatePrompt(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['prompts'] })
      queryClient.invalidateQueries({ queryKey: ['prompt-categories'] })
      setFormOpen(false)
    },
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => deletePrompt(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['prompts'] })
      setDeleteConfirm(null)
    },
  })

  const toggleMut = useMutation({
    mutationFn: (id: string) => togglePrompt(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['prompts'] }),
  })

  const duplicateMut = useMutation({
    mutationFn: (id: string) => duplicatePrompt(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['prompts'] }),
  })

  // Handlers
  const openCreate = () => {
    setEditingId(null)
    form.reset(EMPTY_FORM)
    setTagInput('')
    setFormOpen(true)
  }

  const openEdit = (item: PromptTemplateItem) => {
    setEditingId(item.id)
    form.reset({
      name: item.name,
      description: item.description || '',
      template_type: item.template_type,
      content: item.content,
      user_template: '',
      variables: item.variables || [],
    })
    setTagInput('')
    setFormOpen(true)
  }

  const onSubmit = (values: PromptFormValues) => {
    const payload: PromptCreatePayload = {
      name: values.name,
      description: values.description || null,
      template_type: values.template_type,
      content: values.content,
      variables: values.variables.length > 0 ? values.variables : null,
    }
    if (editingId) {
      updateMut.mutate({ id: editingId, data: payload })
    } else {
      createMut.mutate(payload)
    }
  }

  const handleAddVariable = () => {
    const v = tagInput.trim()
    if (v && !variables.includes(v)) {
      form.setValue('variables', [...variables, v])
    }
    setTagInput('')
  }

  const handleRemoveVariable = (idx: number) => {
    form.setValue(
      'variables',
      variables.filter((_, i) => i !== idx),
    )
  }

  const handleTagKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      handleAddVariable()
    }
  }

  const handleRender = async () => {
    if (!renderTarget) return
    setRendering(true)
    try {
      const res = await renderPrompt({
        template_id: renderTarget.id,
        variables: renderVars,
      })
      setRenderResult(res.data.data.rendered)
    } catch {
      setRenderResult(t('messages.renderFailed'))
    } finally {
      setRendering(false)
    }
  }

  const openRenderDialog = (item: PromptTemplateItem) => {
    setRenderTarget(item)
    setRenderVars({})
    setRenderResult(null)
    setRenderOpen(true)
  }

  // -------- AI 自动生成提示词 --------
  const openAIGenerate = () => {
    setAiDescription('')
    setAiCategory(categoryFilter || 'general')
    setAiTone('professional')
    setAiLanguage('zh')
    setAiResult(null)
    setAiError('')
    setAiOpen(true)
  }

  const handleAIGenerate = async () => {
    if (aiDescription.trim().length < 2) {
      setAiError(t('messages.aiDescRequired'))
      return
    }
    setAiGenerating(true)
    setAiError('')
    setAiResult(null)
    try {
      const res = await aiGeneratePrompt({
        description: aiDescription.trim(),
        template_type: aiCategory,
        tone: aiTone,
        language: aiLanguage,
      })
      const d = res.data.data
      setAiResult({
        name: d.name,
        description: d.description,
        content: d.content,
        variables: d.variables,
      })
    } catch (err) {
      setAiError(getErrorMessage(err, t('messages.aiGenerateFailed')))
    } finally {
      setAiGenerating(false)
    }
  }

  const handleAISaveAndEdit = () => {
    if (!aiResult) return
    // 把 AI 生成结果填入新建表单，让用户继续编辑后保存
    form.reset({
      name: aiResult.name,
      description: aiResult.description,
      template_type: aiCategory,
      content: aiResult.content,
      user_template: '',
      variables: aiResult.variables,
    })
    setTagInput('')
    setAiOpen(false)
    setFormOpen(true)
  }

  // -------- 导出 --------
  const handleExport = async () => {
    try {
      const res = await exportPrompts(categoryFilter)
      const data = res.data.data
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: 'application/json',
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)
      a.download = `finpilot-prompts-${ts}.json`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (err) {
      setImportSuccess(false)
      setImportMessage(getErrorMessage(err, t('messages.exportFailed')))
    }
  }

  // -------- 导入 --------
  const handleImportFile = async (file: File) => {
    setImportBusy(true)
    setImportMessage('')
    setImportSuccess(false)
    try {
      const text = await file.text()
      const parsed = JSON.parse(text) as { items?: PromptExportItem[] } | PromptExportItem[]
      const items: PromptExportItem[] = Array.isArray(parsed) ? parsed : parsed.items || []
      if (items.length === 0) {
        setImportMessage(t('messages.importEmpty'))
        return
      }
      const res = await importPrompts(items)
      const d = res.data.data
      setImportSuccess(true)
      setImportMessage(
        t('messages.importSuccess', { created: d.created_count, failed: d.failed_count }),
      )
      queryClient.invalidateQueries({ queryKey: ['prompts'] })
      queryClient.invalidateQueries({ queryKey: ['prompt-categories'] })
    } catch (err) {
      setImportSuccess(false)
      setImportMessage(getErrorMessage(err, t('messages.importFailed')))
    } finally {
      setImportBusy(false)
    }
  }

  const submitLabel = editingId ? t('form.save') : t('form.create')
  const mutError =
    createMut.error || updateMut.error
      ? getErrorMessage(createMut.error || updateMut.error, t('messages.mutationFailed'))
      : ''

  useEffect(() => {
    setPage(1)
  }, [search, categoryFilter, statusFilter])

  return (
    <div className="admin-prompt-management">
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
              placeholder={t('toolbar.searchPlaceholder')}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="admin-search-input"
            />
          </div>
          <select
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
            className="admin-filter-select"
          >
            <option value="">{t('toolbar.allCategories')}</option>
            {categories.map((c) => (
              <option key={c} value={c}>
                {t(`categories.${c}`, { defaultValue: c })}
              </option>
            ))}
          </select>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="admin-filter-select"
          >
            <option value="">{t('toolbar.allStatus')}</option>
            <option value="active">{t('toolbar.statusActive')}</option>
            <option value="inactive">{t('toolbar.statusInactive')}</option>
          </select>
        </div>
        <div className="admin-toolbar-right">
          <button
            className="btn btn-secondary"
            onClick={openAIGenerate}
            title={t('toolbar.aiGenerateTitle')}
          >
            <ICONS.agent size={14} /> {t('toolbar.aiGenerate')}
          </button>
          <label
            className="btn btn-secondary"
            style={{ cursor: importBusy ? 'wait' : 'pointer' }}
            title={t('toolbar.importTitle')}
          >
            <ICONS.documents size={14} /> {t('toolbar.import')}
            <input
              type="file"
              accept="application/json,.json"
              style={{ display: 'none' }}
              disabled={importBusy}
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) handleImportFile(f)
                e.target.value = ''
              }}
            />
          </label>
          <button
            className="btn btn-secondary"
            onClick={handleExport}
            title={t('toolbar.exportTitle')}
          >
            <ICONS.reports size={14} /> {t('toolbar.export')}
          </button>
          <button className="btn btn-primary" onClick={openCreate}>
            <ICONS.dashboard size={14} /> {t('toolbar.create')}
          </button>
        </div>
      </div>

      {importMessage && (
        <div
          className="admin-error"
          style={{
            marginBottom: 12,
            color: importSuccess ? '#10b981' : undefined,
          }}
        >
          {importMessage}
        </div>
      )}

      {/* Content */}
      {isLoading ? (
        <Loading />
      ) : isError ? (
        <div className="admin-error">{getErrorMessage(error, t('messages.loadFailed'))}</div>
      ) : items.length === 0 ? (
        <EmptyState title={t('empty.noPrompts')} />
      ) : (
        <>
          <div className="admin-table-wrapper">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>{t('table.name')}</th>
                  <th>{t('table.category')}</th>
                  <th style={{ width: 100, textAlign: 'center' }}>{t('table.varCount')}</th>
                  <th style={{ width: 80, textAlign: 'center' }}>{t('table.status')}</th>
                  <th style={{ width: 160 }}>{t('table.updatedAt')}</th>
                  <th style={{ width: 220, textAlign: 'right' }}>{t('table.actions')}</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id}>
                    <td className="admin-table-name">
                      <span className="admin-model-display">{item.name}</span>
                      {item.is_system && (
                        <span className="admin-system-tag">{t('table.systemTag')}</span>
                      )}
                    </td>
                    <td>
                      <span
                        className="admin-category-badge"
                        style={{
                          backgroundColor:
                            CATEGORY_COLORS[item.template_type] || '#6b7280',
                        }}
                      >
                        {t(`categories.${item.template_type}`, { defaultValue: item.template_type })}
                      </span>
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      {(item.variables || []).length}
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      <button
                        className={`admin-toggle ${item.is_active ? 'active' : ''}`}
                        onClick={() => toggleMut.mutate(item.id)}
                        title={item.is_active ? t('toggle.activeTitle') : t('toggle.inactiveTitle')}
                      >
                        <span className="admin-toggle-knob" />
                      </button>
                    </td>
                    <td className="admin-table-mono">
                      {formatDateTime(item.updated_at)}
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <div className="admin-actions">
                        <button
                          className="admin-action-btn"
                          title={t('actions.renderTest')}
                          onClick={() => openRenderDialog(item)}
                        >
                          <ICONS.send size={14} />
                        </button>
                        <button
                          className="admin-action-btn"
                          title={t('actions.duplicate')}
                          onClick={() => duplicateMut.mutate(item.id)}
                        >
                          <ICONS.copy size={14} />
                        </button>
                        <button
                          className="admin-action-btn"
                          title={t('actions.edit')}
                          onClick={() => openEdit(item)}
                        >
                          <ICONS.settings size={14} />
                        </button>
                        {!item.is_system && (
                          <button
                            className="admin-action-btn danger"
                            title={t('actions.delete')}
                            onClick={() => setDeleteConfirm(item.id)}
                          >
                            <ICONS.close size={14} />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="admin-pagination">
              <button disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
                {t('pagination.prev')}
              </button>
              <span>
                {t('pagination.info', { page, totalPages, total })}
              </span>
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
                {t('form.cancel')}
              </button>
              <button
                className="btn btn-primary"
                onClick={form.handleSubmit(onSubmit)}
                disabled={createMut.isPending || updateMut.isPending}
              >
                {createMut.isPending || updateMut.isPending ? t('form.saving') : submitLabel}
              </button>
            </div>
          }
        >
          <form className="admin-form" style={{ maxWidth: 800 }} onSubmit={form.handleSubmit(onSubmit)}>
            {mutError && <div className="admin-form-error">{mutError}</div>}

            <div className="admin-form-row">
              <label className="admin-form-label">{t('form.name')}</label>
              <input className="admin-form-input" {...form.register('name')} placeholder={t('form.namePlaceholder')} />
            </div>

            <div className="admin-form-row">
              <label className="admin-form-label">{t('form.description')}</label>
              <input className="admin-form-input" {...form.register('description')} placeholder={t('form.descriptionPlaceholder')} />
            </div>

            <div className="admin-form-row">
              <label className="admin-form-label">{t('form.category')}</label>
              <select className="admin-form-select" {...form.register('template_type')}>
                {categories.map((c) => (
                  <option key={c} value={c}>
                    {t(`categories.${c}`, { defaultValue: c })}
                  </option>
                ))}
                {categories.length === 0 && (
                  <>
                    <option value="chat">{t('categories.chat', { defaultValue: 'chat' })}</option>
                    <option value="analysis">{t('categories.analysis', { defaultValue: 'analysis' })}</option>
                    <option value="report">{t('categories.report', { defaultValue: 'report' })}</option>
                    <option value="sql_generation">{t('categories.sql_generation', { defaultValue: 'sql_generation' })}</option>
                    <option value="audit">{t('categories.audit', { defaultValue: 'audit' })}</option>
                    <option value="general">{t('categories.general', { defaultValue: 'general' })}</option>
                  </>
                )}
              </select>
            </div>

            <div className="admin-form-row">
              <label className="admin-form-label">{t('form.systemPrompt')}</label>
              <textarea
                className="admin-form-textarea"
                rows={6}
                {...form.register('content')}
                placeholder={t('form.systemPromptPlaceholder')}
                style={{ fontFamily: 'monospace', fontSize: 13 }}
              />
            </div>

            <div className="admin-form-row">
              <label className="admin-form-label">{t('form.userTemplate')}</label>
              <textarea
                className="admin-form-textarea"
                rows={8}
                {...form.register('user_template')}
                placeholder={t('form.userTemplatePlaceholder')}
                style={{ fontFamily: 'monospace', fontSize: 13 }}
              />
            </div>

            <div className="admin-form-row">
              <label className="admin-form-label">{t('form.variables')}</label>
              <div className="admin-tag-input-wrapper">
                <div className="admin-tags">
                  {variables.map((v, i) => (
                    <span key={i} className="admin-tag">
                      {`{${v}}`}
                      <button
                        type="button"
                        className="admin-tag-remove"
                        onClick={() => handleRemoveVariable(i)}
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
                <div className="admin-tag-input-row">
                  <input
                    className="admin-form-input"
                    value={tagInput}
                    onChange={(e) => setTagInput(e.target.value)}
                    onKeyDown={handleTagKeyDown}
                    placeholder={t('form.varPlaceholder')}
                  />
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={handleAddVariable}
                    style={{ whiteSpace: 'nowrap' }}
                  >
                    {t('form.addVar')}
                  </button>
                </div>
              </div>
            </div>
          </form>
        </Modal>
      )}

      {/* Render Test Dialog */}
      {renderOpen && renderTarget && (
        <Modal
          title={t('render.title', { name: renderTarget.name })}
          onClose={() => setRenderOpen(false)}
        >
          <div className="admin-render-body">
            <div className="admin-render-vars">
              <h4>{t('render.varsTitle')}</h4>
              {(renderTarget.variables || []).map((v) => (
                <div key={v} className="admin-form-row">
                  <label className="admin-form-label">{`{${v}}`}</label>
                  <input
                    className="admin-form-input"
                    value={renderVars[v] || ''}
                    onChange={(e) =>
                      setRenderVars((prev) => ({ ...prev, [v]: e.target.value }))
                    }
                    placeholder={t('render.varPlaceholder', { varName: v })}
                  />
                </div>
              ))}
              {(renderTarget.variables || []).length === 0 && (
                <p className="admin-form-hint">{t('render.noVars')}</p>
              )}
            </div>

            <div className="admin-render-actions">
              <button className="btn btn-primary" onClick={handleRender} disabled={rendering}>
                {rendering ? t('render.rendering') : t('render.render')}
              </button>
            </div>

            {renderResult !== null && (
              <div className="admin-render-result">
                <h4>{t('render.resultTitle')}</h4>
                <pre className="admin-render-output">{renderResult}</pre>
              </div>
            )}
          </div>
        </Modal>
      )}

      {/* Delete Confirm Dialog */}
      {deleteConfirm && (
        <Modal title={t('delete.title')} onClose={() => setDeleteConfirm(null)}>
          <p style={{ marginBottom: 16 }}>{t('delete.message')}</p>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button className="btn btn-secondary" onClick={() => setDeleteConfirm(null)}>
              {t('delete.cancel')}
            </button>
            <button
              className="btn btn-danger"
              onClick={() => deleteMut.mutate(deleteConfirm)}
              disabled={deleteMut.isPending}
            >
              {deleteMut.isPending ? t('delete.deleting') : t('delete.confirm')}
            </button>
          </div>
          {deleteMut.error && (
            <div className="admin-form-error" style={{ marginTop: 8 }}>
              {getErrorMessage(deleteMut.error, t('messages.deleteFailed'))}
            </div>
          )}
        </Modal>
      )}

      {/* AI 自动生成提示词 Dialog */}
      {aiOpen && (
        <Modal
          title={t('ai.title')}
          onClose={() => setAiOpen(false)}
          footer={
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button className="btn btn-secondary" onClick={() => setAiOpen(false)}>
                {t('ai.close')}
              </button>
              {!aiResult ? (
                <button
                  className="btn btn-primary"
                  onClick={handleAIGenerate}
                  disabled={aiGenerating || aiDescription.trim().length < 2}
                >
                  {aiGenerating ? t('ai.generating') : t('ai.generate')}
                </button>
              ) : (
                <button className="btn btn-primary" onClick={handleAISaveAndEdit}>
                  {t('ai.fillForm')}
                </button>
              )}
            </div>
          }
        >
          <div className="admin-form" style={{ maxWidth: 720 }}>
            <p
              className="text-muted"
              style={{ fontSize: 12, marginBottom: 12 }}
            >
              {t('ai.hint')}
            </p>

            <div className="admin-form-row">
              <label className="admin-form-label">{t('ai.descLabel')}</label>
              <textarea
                className="admin-form-input"
                rows={3}
                placeholder={t('ai.descPlaceholder')}
                value={aiDescription}
                onChange={(e) => setAiDescription(e.target.value)}
              />
            </div>

            <div
              className="admin-form-row"
              style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}
            >
              <div>
                <label className="admin-form-label">{t('ai.categoryLabel')}</label>
                <select
                  className="admin-form-input"
                  value={aiCategory}
                  onChange={(e) => setAiCategory(e.target.value)}
                >
                  <option value="general">{t('categories.general')}</option>
                  <option value="chat">{t('categories.chat')}</option>
                  <option value="analysis">{t('categories.analysis')}</option>
                  <option value="report">{t('categories.report')}</option>
                  <option value="sql_generation">{t('categories.sql_generation')}</option>
                  <option value="audit">{t('categories.audit')}</option>
                  <option value="query">{t('categories.query')}</option>
                  <option value="custom">{t('categories.custom')}</option>
                </select>
              </div>
              <div>
                <label className="admin-form-label">{t('ai.toneLabel')}</label>
                <select
                  className="admin-form-input"
                  value={aiTone}
                  onChange={(e) =>
                    setAiTone(e.target.value as 'professional' | 'concise' | 'friendly')
                  }
                >
                  <option value="professional">{t('tones.professional')}</option>
                  <option value="concise">{t('tones.concise')}</option>
                  <option value="friendly">{t('tones.friendly')}</option>
                </select>
              </div>
              <div>
                <label className="admin-form-label">{t('ai.languageLabel')}</label>
                <select
                  className="admin-form-input"
                  value={aiLanguage}
                  onChange={(e) => setAiLanguage(e.target.value as 'zh' | 'en')}
                >
                  <option value="zh">{t('languages.zh')}</option>
                  <option value="en">{t('languages.en')}</option>
                </select>
              </div>
            </div>

            {aiError && (
              <div className="admin-form-error" style={{ marginTop: 8 }}>
                {aiError}
              </div>
            )}

            {aiResult && (
              <div
                style={{
                  marginTop: 16,
                  padding: 12,
                  border: '1px solid var(--color-border)',
                  borderRadius: 4,
                  background: 'var(--color-surface-raised)',
                }}
              >
                <h4 style={{ margin: '0 0 8px' }}>{t('ai.previewTitle')}</h4>
                <div style={{ marginBottom: 6 }}>
                  <strong>{t('ai.previewName')}</strong>
                  {aiResult.name}
                </div>
                {aiResult.description && (
                  <div style={{ marginBottom: 6 }}>
                    <strong>{t('ai.previewDescription')}</strong>
                    {aiResult.description}
                  </div>
                )}
                {aiResult.variables.length > 0 && (
                  <div style={{ marginBottom: 6 }}>
                    <strong>{t('ai.previewVariables')}</strong>
                    {aiResult.variables.map((v) => (
                      <span
                        key={v}
                        style={{
                          display: 'inline-block',
                          padding: '2px 8px',
                          marginRight: 4,
                          marginBottom: 4,
                          background: 'var(--color-primary-subtle)',
                          color: 'var(--color-primary-ink)',
                          borderRadius: 2,
                          fontSize: 12,
                        }}
                      >
                        {`{{${v}}}`}
                      </span>
                    ))}
                  </div>
                )}
                <div>
                  <strong>{t('ai.previewSystemPrompt')}</strong>
                  <pre
                    style={{
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                      background: 'var(--color-bg)',
                      padding: 8,
                      borderRadius: 2,
                      maxHeight: 240,
                      overflow: 'auto',
                      fontSize: 12,
                    }}
                  >
                    {aiResult.content}
                  </pre>
                </div>
              </div>
            )}
          </div>
        </Modal>
      )}

    </div>
  )
}
