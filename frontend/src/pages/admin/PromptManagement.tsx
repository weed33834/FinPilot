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

const promptFormSchema = z.object({
  name: z.string().min(1, '请输入模板名称'),
  description: z.string().optional(),
  template_type: z.string().min(1, '请选择分类'),
  content: z.string().min(1, '请输入 System Prompt'),
  user_template: z.string().optional(),
  variables: z.array(z.string()).default([]),
})

type PromptFormValues = z.infer<typeof promptFormSchema>

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
      setRenderResult('渲染失败')
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
      setAiError('请输入至少 2 个字符的需求描述')
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
      setAiError(getErrorMessage(err, 'AI 生成失败，请检查默认 LLM 供应商配置'))
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
      setImportMessage(getErrorMessage(err, '导出失败'))
    }
  }

  // -------- 导入 --------
  const handleImportFile = async (file: File) => {
    setImportBusy(true)
    setImportMessage('')
    try {
      const text = await file.text()
      const parsed = JSON.parse(text) as { items?: PromptExportItem[] } | PromptExportItem[]
      const items: PromptExportItem[] = Array.isArray(parsed) ? parsed : parsed.items || []
      if (items.length === 0) {
        setImportMessage('文件中未找到可导入的提示词')
        return
      }
      const res = await importPrompts(items)
      const d = res.data.data
      setImportMessage(
        `导入完成：成功 ${d.created_count} 条，失败 ${d.failed_count} 条`,
      )
      queryClient.invalidateQueries({ queryKey: ['prompts'] })
      queryClient.invalidateQueries({ queryKey: ['prompt-categories'] })
    } catch (err) {
      setImportMessage(getErrorMessage(err, '导入失败：请确认文件为合法 JSON'))
    } finally {
      setImportBusy(false)
    }
  }

  const submitLabel = editingId ? '保存' : '创建'
  const mutError =
    createMut.error || updateMut.error
      ? getErrorMessage(createMut.error || updateMut.error, '操作失败')
      : ''

  useEffect(() => {
    setPage(1)
  }, [search, categoryFilter, statusFilter])

  return (
    <div className="admin-prompt-management">
      <div className="admin-page-header">
        <h1 className="admin-page-title">提示词管理</h1>
        <p className="admin-page-desc">管理 AI 提示词模板，支持变量占位符、分类筛选和渲染测试。</p>
      </div>

      {/* Toolbar */}
      <div className="admin-toolbar">
        <div className="admin-toolbar-left">
          <div className="admin-search-box">
            <ICONS.search size={14} />
            <input
              type="text"
              placeholder="搜索模板名称..."
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
            <option value="">全部分类</option>
            {categories.map((c) => (
              <option key={c} value={c}>
                {c}
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
          <button
            className="btn btn-secondary"
            onClick={openAIGenerate}
            title="使用 AI 根据自然语言需求生成提示词模板"
          >
            <ICONS.agent size={14} /> AI 生成
          </button>
          <label
            className="btn btn-secondary"
            style={{ cursor: importBusy ? 'wait' : 'pointer' }}
            title="从 JSON 文件批量导入提示词"
          >
            <ICONS.documents size={14} /> 导入
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
            title="导出当前筛选范围下的全部提示词为 JSON"
          >
            <ICONS.reports size={14} /> 导出
          </button>
          <button className="btn btn-primary" onClick={openCreate}>
            <ICONS.dashboard size={14} /> 新建模板
          </button>
        </div>
      </div>

      {importMessage && (
        <div
          className="admin-error"
          style={{
            marginBottom: 12,
            color: importMessage.startsWith('导入完成') ? '#10b981' : undefined,
          }}
        >
          {importMessage}
        </div>
      )}

      {/* Content */}
      {isLoading ? (
        <Loading />
      ) : isError ? (
        <div className="admin-error">{getErrorMessage(error, '加载模板列表失败')}</div>
      ) : items.length === 0 ? (
        <EmptyState title="暂无提示词模板" />
      ) : (
        <>
          <div className="admin-table-wrapper">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>名称</th>
                  <th>分类</th>
                  <th style={{ width: 100, textAlign: 'center' }}>变量数</th>
                  <th style={{ width: 80, textAlign: 'center' }}>状态</th>
                  <th style={{ width: 160 }}>更新时间</th>
                  <th style={{ width: 220, textAlign: 'right' }}>操作</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id}>
                    <td className="admin-table-name">
                      <span className="admin-model-display">{item.name}</span>
                      {item.is_system && (
                        <span className="admin-system-tag">系统</span>
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
                        {item.template_type}
                      </span>
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      {(item.variables || []).length}
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
                    <td className="admin-table-mono">
                      {formatDateTime(item.updated_at)}
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <div className="admin-actions">
                        <button
                          className="admin-action-btn"
                          title="测试渲染"
                          onClick={() => openRenderDialog(item)}
                        >
                          <ICONS.send size={14} />
                        </button>
                        <button
                          className="admin-action-btn"
                          title="复制"
                          onClick={() => duplicateMut.mutate(item.id)}
                        >
                          <ICONS.copy size={14} />
                        </button>
                        <button
                          className="admin-action-btn"
                          title="编辑"
                          onClick={() => openEdit(item)}
                        >
                          <ICONS.settings size={14} />
                        </button>
                        {!item.is_system && (
                          <button
                            className="admin-action-btn danger"
                            title="删除"
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
          title={editingId ? '编辑提示词模板' : '新建提示词模板'}
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
          <form className="admin-form" style={{ maxWidth: 800 }} onSubmit={form.handleSubmit(onSubmit)}>
            {mutError && <div className="admin-form-error">{mutError}</div>}

            <div className="admin-form-row">
              <label className="admin-form-label">模板名称</label>
              <input className="admin-form-input" {...form.register('name')} placeholder="如 财务分析报告模板" />
            </div>

            <div className="admin-form-row">
              <label className="admin-form-label">描述</label>
              <input className="admin-form-input" {...form.register('description')} placeholder="模板用途说明" />
            </div>

            <div className="admin-form-row">
              <label className="admin-form-label">分类</label>
              <select className="admin-form-select" {...form.register('template_type')}>
                {categories.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
                {categories.length === 0 && (
                  <>
                    <option value="chat">chat</option>
                    <option value="analysis">analysis</option>
                    <option value="report">report</option>
                    <option value="sql_generation">sql_generation</option>
                    <option value="audit">audit</option>
                    <option value="general">general</option>
                  </>
                )}
              </select>
            </div>

            <div className="admin-form-row">
              <label className="admin-form-label">System Prompt</label>
              <textarea
                className="admin-form-textarea"
                rows={6}
                {...form.register('content')}
                placeholder="输入 System Prompt，支持 {variable} 占位符"
                style={{ fontFamily: 'monospace', fontSize: 13 }}
              />
            </div>

            <div className="admin-form-row">
              <label className="admin-form-label">User Prompt Template（可选）</label>
              <textarea
                className="admin-form-textarea"
                rows={8}
                {...form.register('user_template')}
                placeholder="User prompt 模板..."
                style={{ fontFamily: 'monospace', fontSize: 13 }}
              />
            </div>

            <div className="admin-form-row">
              <label className="admin-form-label">变量</label>
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
                    placeholder="输入变量名后按 Enter 添加"
                  />
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={handleAddVariable}
                    style={{ whiteSpace: 'nowrap' }}
                  >
                    添加
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
          title={`测试渲染 — ${renderTarget.name}`}
          onClose={() => setRenderOpen(false)}
        >
          <div className="admin-render-body">
            <div className="admin-render-vars">
              <h4>变量输入</h4>
              {(renderTarget.variables || []).map((v) => (
                <div key={v} className="admin-form-row">
                  <label className="admin-form-label">{`{${v}}`}</label>
                  <input
                    className="admin-form-input"
                    value={renderVars[v] || ''}
                    onChange={(e) =>
                      setRenderVars((prev) => ({ ...prev, [v]: e.target.value }))
                    }
                    placeholder={`输入 ${v} 的值`}
                  />
                </div>
              ))}
              {(renderTarget.variables || []).length === 0 && (
                <p className="admin-form-hint">此模板没有变量。</p>
              )}
            </div>

            <div className="admin-render-actions">
              <button className="btn btn-primary" onClick={handleRender} disabled={rendering}>
                {rendering ? '渲染中...' : '渲染'}
              </button>
            </div>

            {renderResult !== null && (
              <div className="admin-render-result">
                <h4>渲染结果</h4>
                <pre className="admin-render-output">{renderResult}</pre>
              </div>
            )}
          </div>
        </Modal>
      )}

      {/* Delete Confirm Dialog */}
      {deleteConfirm && (
        <Modal title="确认删除" onClose={() => setDeleteConfirm(null)}>
          <p style={{ marginBottom: 16 }}>确定要删除此提示词模板吗？此操作不可撤销。</p>
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

      {/* AI 自动生成提示词 Dialog */}
      {aiOpen && (
        <Modal
          title="AI 自动生成提示词"
          onClose={() => setAiOpen(false)}
          footer={
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button className="btn btn-secondary" onClick={() => setAiOpen(false)}>
                关闭
              </button>
              {!aiResult ? (
                <button
                  className="btn btn-primary"
                  onClick={handleAIGenerate}
                  disabled={aiGenerating || aiDescription.trim().length < 2}
                >
                  {aiGenerating ? '生成中...(约 10-20 秒)' : '调用 AI 生成'}
                </button>
              ) : (
                <button className="btn btn-primary" onClick={handleAISaveAndEdit}>
                  填入表单继续编辑
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
              用自然语言描述需求，AI 将调用默认 LLM 生成结构化提示词模板（含变量占位符）。
              生成后可直接填入表单继续编辑。
            </p>

            <div className="admin-form-row">
              <label className="admin-form-label">需求描述 *</label>
              <textarea
                className="admin-form-input"
                rows={3}
                placeholder="例如：生成一个用于财报分析的提示词，输入公司名和财报数据，输出结构化的财务摘要和风险评估"
                value={aiDescription}
                onChange={(e) => setAiDescription(e.target.value)}
              />
            </div>

            <div
              className="admin-form-row"
              style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}
            >
              <div>
                <label className="admin-form-label">目标分类</label>
                <select
                  className="admin-form-input"
                  value={aiCategory}
                  onChange={(e) => setAiCategory(e.target.value)}
                >
                  <option value="general">通用</option>
                  <option value="chat">对话</option>
                  <option value="analysis">分析</option>
                  <option value="report">报告</option>
                  <option value="sql_generation">SQL 生成</option>
                  <option value="audit">审计</option>
                  <option value="query">查询</option>
                  <option value="custom">自定义</option>
                </select>
              </div>
              <div>
                <label className="admin-form-label">风格</label>
                <select
                  className="admin-form-input"
                  value={aiTone}
                  onChange={(e) =>
                    setAiTone(e.target.value as 'professional' | 'concise' | 'friendly')
                  }
                >
                  <option value="professional">专业</option>
                  <option value="concise">简洁</option>
                  <option value="friendly">友好</option>
                </select>
              </div>
              <div>
                <label className="admin-form-label">输出语言</label>
                <select
                  className="admin-form-input"
                  value={aiLanguage}
                  onChange={(e) => setAiLanguage(e.target.value as 'zh' | 'en')}
                >
                  <option value="zh">中文</option>
                  <option value="en">英文</option>
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
                <h4 style={{ margin: '0 0 8px' }}>生成结果预览</h4>
                <div style={{ marginBottom: 6 }}>
                  <strong>名称：</strong>
                  {aiResult.name}
                </div>
                {aiResult.description && (
                  <div style={{ marginBottom: 6 }}>
                    <strong>描述：</strong>
                    {aiResult.description}
                  </div>
                )}
                {aiResult.variables.length > 0 && (
                  <div style={{ marginBottom: 6 }}>
                    <strong>变量：</strong>
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
                  <strong>System Prompt：</strong>
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
