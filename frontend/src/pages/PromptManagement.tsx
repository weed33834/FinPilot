import { useEffect, useState } from 'react'
import Modal from '../components/ui/Modal.tsx'
import ConfirmDialog from '../components/ui/ConfirmDialog.tsx'
import Loading from '../components/ui/Loading.tsx'
import EmptyState from '../components/ui/EmptyState.tsx'
import { api } from '../api/client.ts'
import { getErrorMessage } from '../utils/errors.ts'
import { formatDateTime } from '../utils/format.ts'
import type { DataResponse, PaginatedResponse } from '../types/report.ts'

interface PromptTemplate {
  id: string
  name: string
  category: string
  system_prompt: string
  user_prompt_template: string
  variables: string[]
  is_active: boolean
  created_at: string
  updated_at: string
}

interface PromptForm {
  name: string
  category: string
  system_prompt: string
  user_prompt_template: string
  variables: string[]
  is_active: boolean
}

const CATEGORIES = ['chat', 'analysis', 'report', 'sql_generation', 'default']

const EMPTY_FORM: PromptForm = {
  name: '',
  category: 'chat',
  system_prompt: '',
  user_prompt_template: '',
  variables: [],
  is_active: true,
}

export default function PromptManagement() {
  const [prompts, setPrompts] = useState<PromptTemplate[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('')
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<PromptTemplate | null>(null)
  const [form, setForm] = useState<PromptForm>(EMPTY_FORM)
  const [submitting, setSubmitting] = useState(false)
  const [actingId, setActingId] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [varInput, setVarInput] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<PromptTemplate | null>(null)

  // Render test
  const [renderModalOpen, setRenderModalOpen] = useState(false)
  const [renderTarget, setRenderTarget] = useState<PromptTemplate | null>(null)
  const [renderInputs, setRenderInputs] = useState<Record<string, string>>({})
  const [renderResult, setRenderResult] = useState('')

  const fetchPrompts = async () => {
    setLoading(true)
    setError('')
    try {
      const params: Record<string, unknown> = { page, page_size: 20 }
      if (categoryFilter) params.category = categoryFilter
      if (search) params.search = search
      const response = await api.get<DataResponse<PaginatedResponse<PromptTemplate>>>('/prompts', { params })
      setPrompts(response.data.data?.items || [])
      setTotal(response.data.data?.total || 0)
    } catch (err) {
      setError(getErrorMessage(err, '加载模板列表失败'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchPrompts()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, categoryFilter])

  const openCreate = () => {
    setEditing(null)
    setForm(EMPTY_FORM)
    setModalOpen(true)
  }

  const openEdit = (prompt: PromptTemplate) => {
    setEditing(prompt)
    setForm({
      name: prompt.name,
      category: prompt.category,
      system_prompt: prompt.system_prompt,
      user_prompt_template: prompt.user_prompt_template,
      variables: [...prompt.variables],
      is_active: prompt.is_active,
    })
    setModalOpen(true)
  }

  const handleSave = async () => {
    setSubmitting(true)
    setError('')
    try {
      if (editing) {
        await api.put(`/prompts/${editing.id}`, form)
      } else {
        await api.post('/prompts', form)
      }
      setModalOpen(false)
      fetchPrompts()
    } catch (err) {
      setError(getErrorMessage(err, '保存模板失败'))
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async (prompt: PromptTemplate) => {
    setActingId(prompt.id)
    try {
      await api.delete(`/prompts/${prompt.id}`)
      fetchPrompts()
    } catch (err) {
      setError(getErrorMessage(err, '删除模板失败'))
    } finally {
      setActingId(null)
    }
  }

  const handleToggle = async (prompt: PromptTemplate) => {
    setActingId(prompt.id)
    try {
      await api.put(`/prompts/${prompt.id}/toggle`)
      fetchPrompts()
    } catch (err) {
      setError(getErrorMessage(err, '切换状态失败'))
    } finally {
      setActingId(null)
    }
  }

  const handleDuplicate = async (prompt: PromptTemplate) => {
    setActingId(prompt.id)
    try {
      await api.post(`/prompts/${prompt.id}/duplicate`)
      fetchPrompts()
    } catch (err) {
      setError(getErrorMessage(err, '复制模板失败'))
    } finally {
      setActingId(null)
    }
  }

  const openRender = (prompt: PromptTemplate) => {
    setRenderTarget(prompt)
    setRenderInputs(Object.fromEntries(prompt.variables.map((v) => [v, ''])))
    setRenderResult('')
    setRenderModalOpen(true)
  }

  const handleRender = async () => {
    if (!renderTarget) return
    setSubmitting(true)
    try {
      const response = await api.post<DataResponse<{ rendered: string }>>(`/prompts/${renderTarget.id}/render`, { variables: renderInputs })
      setRenderResult(response.data.data?.rendered || '')
    } catch (err) {
      setError(getErrorMessage(err, '渲染失败'))
    } finally {
      setSubmitting(false)
    }
  }

  const addVariable = () => {
    const v = varInput.trim()
    if (v && !form.variables.includes(v)) {
      setForm({ ...form, variables: [...form.variables, v] })
    }
    setVarInput('')
  }

  const removeVariable = (v: string) => {
    setForm({ ...form, variables: form.variables.filter((x) => x !== v) })
  }

  const handleSearch = () => { setPage(1); fetchPrompts() }

  const totalPages = Math.ceil(total / 20)

  return (
    <div className="container">
      <div className="page-header">
        <h1>提示词模板管理</h1>
        <button type="button" onClick={openCreate}>新建模板</button>
      </div>

      {error && <div className="alert alert-error mb-4" role="alert">{error}</div>}

      <div className="flex gap-2 mb-4" style={{ alignItems: 'center' }}>
        <input value={search} onChange={(e) => setSearch(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && handleSearch()} placeholder="搜索模板名称..." style={{ maxWidth: 240 }} />
        <select value={categoryFilter} onChange={(e) => { setCategoryFilter(e.target.value); setPage(1) }}>
          <option value="">全部分类</option>
          {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <button type="button" className="secondary" onClick={handleSearch}>搜索</button>
      </div>

      {loading ? (
        <Loading text="加载模板中..." />
      ) : prompts.length === 0 ? (
        <EmptyState title="暂无提示词模板" description="点击「新建模板」创建第一个模板。" />
      ) : (
        <>
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>名称</th>
                  <th>分类</th>
                  <th>变量数</th>
                  <th>状态</th>
                  <th>更新时间</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {prompts.map((p) => (
                  <tr key={p.id}>
                    <td>{p.name}</td>
                    <td><span className="badge">{p.category}</span></td>
                    <td>{p.variables.length}</td>
                    <td>{p.is_active ? <span className="badge success">启用</span> : <span className="badge rejected">停用</span>}</td>
                    <td className="text-sm text-muted">{formatDateTime(p.updated_at)}</td>
                    <td>
                      <div className="action-group">
                        <button type="button" className="secondary" onClick={() => openRender(p)}>渲染</button>
                        <button type="button" className="secondary" onClick={() => handleToggle(p)} disabled={actingId === p.id}>{p.is_active ? '停用' : '启用'}</button>
                        <button type="button" className="secondary" onClick={() => handleDuplicate(p)} disabled={actingId === p.id}>复制</button>
                        <button type="button" className="secondary" onClick={() => openEdit(p)}>编辑</button>
                        <button type="button" className="danger" onClick={() => setDeleteTarget(p)} disabled={actingId === p.id}>删除</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {totalPages > 1 && (
            <div className="pagination">
              <button type="button" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>上一页</button>
              <span className="text-sm text-muted mx-2">第 {page}/{totalPages} 页，共 {total} 条</span>
              <button type="button" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>下一页</button>
            </div>
          )}
        </>
      )}

      {modalOpen && (
        <Modal
          title={editing ? '编辑模板' : '新建模板'}
          onClose={() => setModalOpen(false)}
          footer={
            <>
              <button type="button" className="secondary" onClick={() => setModalOpen(false)}>取消</button>
              <button type="button" onClick={handleSave} disabled={submitting || !form.name}>保存</button>
            </>
          }
        >
          <div className="form-group">
            <label htmlFor="prompt-name">名称</label>
            <input id="prompt-name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="模板名称" />
          </div>
          <div className="form-group">
            <label htmlFor="prompt-category">分类</label>
            <select id="prompt-category" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
              {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div className="form-group">
            <label htmlFor="prompt-system">System Prompt</label>
            <textarea
              id="prompt-system" value={form.system_prompt}
              onChange={(e) => setForm({ ...form, system_prompt: e.target.value })}
              rows={6} style={{ fontFamily: 'monospace', width: '100%' }}
              placeholder="你是专业的财务分析助手..."
            />
          </div>
          <div className="form-group">
            <label htmlFor="prompt-user">User Prompt Template</label>
            <textarea
              id="prompt-user" value={form.user_prompt_template}
              onChange={(e) => setForm({ ...form, user_prompt_template: e.target.value })}
              rows={10} style={{ fontFamily: 'monospace', width: '100%' }}
              placeholder="请分析以下财务数据：\n{{context}}\n\n用户问题：{{query}}"
            />
          </div>
          <div className="form-group">
            <label>变量</label>
            <div className="flex gap-2 mb-2">
              {form.variables.map((v) => (
                <span key={v} className="badge" style={{ cursor: 'pointer' }} onClick={() => removeVariable(v)} title="点击移除">{v} &times;</span>
              ))}
            </div>
            <div className="flex gap-2">
              <input value={varInput} onChange={(e) => setVarInput(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addVariable())} placeholder="输入变量名回车添加" style={{ flex: 1 }} />
              <button type="button" className="secondary" onClick={addVariable}>添加</button>
            </div>
          </div>
          <div className="form-group">
            <label><input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} /> 启用</label>
          </div>
        </Modal>
      )}

      {renderModalOpen && renderTarget && (
        <Modal
          title={`测试渲染 — ${renderTarget.name}`}
          onClose={() => setRenderModalOpen(false)}
          footer={<button type="button" onClick={() => setRenderModalOpen(false)}>关闭</button>}
        >
          <p className="text-sm text-muted mb-3">输入各变量的值后点击渲染查看完整 Prompt。</p>
          {renderTarget.variables.map((v) => (
            <div className="form-group" key={v}>
              <label>{v}</label>
              <input value={renderInputs[v] || ''} onChange={(e) => setRenderInputs({ ...renderInputs, [v]: e.target.value })} />
            </div>
          ))}
          <button type="button" onClick={handleRender} disabled={submitting} className="mb-3">{submitting ? '渲染中...' : '渲染'}</button>
          {renderResult && (
            <div className="form-group">
              <label>渲染结果</label>
              <pre style={{ background: 'var(--color-bg-secondary)', padding: '1rem', borderRadius: 8, whiteSpace: 'pre-wrap', fontSize: '0.85rem', maxHeight: 400, overflow: 'auto' }}>{renderResult}</pre>
            </div>
          )}
        </Modal>
      )}

      <ConfirmDialog
        open={!!deleteTarget}
        title="确认删除"
        message={deleteTarget ? <>确定要删除模板「<strong>{deleteTarget.name}</strong>」吗？</> : null}
        confirmText="确认删除"
        variant="danger"
        onConfirm={async () => {
          if (deleteTarget) {
            await handleDelete(deleteTarget)
            setDeleteTarget(null)
          }
        }}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  )
}
