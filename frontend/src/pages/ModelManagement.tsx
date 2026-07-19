import { useEffect, useState } from 'react'
import Modal from '../components/ui/Modal.tsx'
import ConfirmDialog from '../components/ui/ConfirmDialog.tsx'
import Loading from '../components/ui/Loading.tsx'
import EmptyState from '../components/ui/EmptyState.tsx'
import { api } from '../api/client.ts'
import { getErrorMessage } from '../utils/errors.ts'
import type { DataResponse, PaginatedResponse } from '../types/report.ts'

interface ModelConfig {
  id: string
  provider: string
  model_name: string
  display_name: string
  api_base: string
  is_default: boolean
  is_active: boolean
  parameters: Record<string, number> | null
  created_at: string
  updated_at: string
}

interface ModelConfigForm {
  provider: string
  model_name: string
  display_name: string
  api_base: string
  api_key: string
  is_default: boolean
  is_active: boolean
  temperature: number
  max_tokens: number
  top_p: number
}

const PROVIDERS = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'google', label: 'Google' },
  { value: 'local', label: 'Local' },
  { value: 'ollama', label: 'Ollama' },
  { value: 'lmstudio', label: 'LM Studio' },
]

const PROVIDER_DEFAULTS: Record<string, string> = {
  openai: 'https://api.openai.com/v1',
  anthropic: 'https://api.anthropic.com',
  google: 'https://generativelanguage.googleapis.com',
  local: 'http://localhost:8080/v1',
  ollama: 'http://localhost:11434',
  lmstudio: 'http://localhost:1234/v1',
}

const EMPTY_FORM: ModelConfigForm = {
  provider: 'ollama',
  model_name: '',
  display_name: '',
  api_base: 'http://localhost:11434',
  api_key: '',
  is_default: false,
  is_active: true,
  temperature: 0.7,
  max_tokens: 4096,
  top_p: 0.9,
}

export default function ModelManagement() {
  const [models, setModels] = useState<ModelConfig[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [providerFilter, setProviderFilter] = useState('')
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<ModelConfig | null>(null)
  const [form, setForm] = useState<ModelConfigForm>(EMPTY_FORM)
  const [submitting, setSubmitting] = useState(false)
  const [actingId, setActingId] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [deleteTarget, setDeleteTarget] = useState<ModelConfig | null>(null)

  const fetchModels = async () => {
    setLoading(true)
    setError('')
    try {
      const params: Record<string, unknown> = { page, page_size: 20 }
      if (providerFilter) params.provider = providerFilter
      if (search) params.search = search
      const response = await api.get<DataResponse<PaginatedResponse<ModelConfig>>>('/models', { params })
      setModels(response.data.data?.items || [])
      setTotal(response.data.data?.total || 0)
    } catch (err) {
      setError(getErrorMessage(err, '加载模型列表失败'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchModels()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, providerFilter])

  const openCreate = () => {
    setEditing(null)
    setForm(EMPTY_FORM)
    setModalOpen(true)
  }

  const openEdit = (model: ModelConfig) => {
    setEditing(model)
    setForm({
      provider: model.provider,
      model_name: model.model_name,
      display_name: model.display_name,
      api_base: model.api_base,
      api_key: '',
      is_default: model.is_default,
      is_active: model.is_active,
      temperature: model.parameters?.temperature ?? 0.7,
      max_tokens: model.parameters?.max_tokens ?? 4096,
      top_p: model.parameters?.top_p ?? 0.9,
    })
    setModalOpen(true)
  }

  const handleSave = async () => {
    setSubmitting(true)
    setError('')
    try {
      const payload = {
        provider: form.provider,
        model_name: form.model_name,
        display_name: form.display_name,
        api_base: form.api_base,
        api_key: form.api_key || undefined,
        is_default: form.is_default,
        is_active: form.is_active,
        parameters: { temperature: form.temperature, max_tokens: form.max_tokens, top_p: form.top_p },
      }
      if (editing) {
        await api.put(`/models/${editing.id}`, payload)
      } else {
        await api.post('/models', payload)
      }
      setModalOpen(false)
      fetchModels()
    } catch (err) {
      setError(getErrorMessage(err, '保存模型失败'))
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async (model: ModelConfig) => {
    setActingId(model.id)
    setError('')
    try {
      await api.delete(`/models/${model.id}`)
      fetchModels()
    } catch (err) {
      setError(getErrorMessage(err, '删除模型失败'))
    } finally {
      setActingId(null)
    }
  }

  const handleToggle = async (model: ModelConfig) => {
    setActingId(model.id)
    try {
      await api.put(`/models/${model.id}/toggle`)
      fetchModels()
    } catch (err) {
      setError(getErrorMessage(err, '切换状态失败'))
    } finally {
      setActingId(null)
    }
  }

  const handleSetDefault = async (model: ModelConfig) => {
    setActingId(model.id)
    try {
      await api.put(`/models/${model.id}/set-default`)
      fetchModels()
    } catch (err) {
      setError(getErrorMessage(err, '设为默认失败'))
    } finally {
      setActingId(null)
    }
  }

  const handleTest = async (model: ModelConfig) => {
    setActingId(model.id)
    try {
      const response = await api.post<DataResponse<{ ok: boolean; message: string }>>(`/models/${model.id}/test`)
      const result = response.data.data
      alert(result?.ok ? '连接成功' : `连接失败: ${result?.message || '未知错误'}`)
    } catch (err) {
      setError(getErrorMessage(err, '测试连接失败'))
    } finally {
      setActingId(null)
    }
  }

  const handleSearch = () => {
    setPage(1)
    fetchModels()
  }

  const totalPages = Math.ceil(total / 20)

  return (
    <div className="container">
      <div className="page-header">
        <h1>模型管理</h1>
        <button type="button" onClick={openCreate}>添加模型</button>
      </div>

      {error && <div className="alert alert-error mb-4" role="alert">{error}</div>}

      <div className="flex gap-2 mb-4" style={{ alignItems: 'center' }}>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
          placeholder="搜索模型名称..."
          style={{ maxWidth: 240 }}
        />
        <select value={providerFilter} onChange={(e) => { setProviderFilter(e.target.value); setPage(1) }}>
          <option value="">全部供应商</option>
          {PROVIDERS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
        </select>
        <button type="button" className="secondary" onClick={handleSearch}>搜索</button>
      </div>

      {loading ? (
        <Loading text="加载模型中..." />
      ) : models.length === 0 ? (
        <EmptyState title="暂无模型配置" description="点击「添加模型」配置第一个 AI 模型。" />
      ) : (
        <>
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>展示名称</th>
                  <th>供应商</th>
                  <th>模型名称</th>
                  <th>API 地址</th>
                  <th>默认</th>
                  <th>状态</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {models.map((model) => (
                  <tr key={model.id}>
                    <td>{model.display_name}</td>
                    <td><span className="badge">{model.provider}</span></td>
                    <td className="text-sm">{model.model_name}</td>
                    <td className="text-sm text-muted">{model.api_base}</td>
                    <td>{model.is_default ? <span className="badge success">默认</span> : '—'}</td>
                    <td>
                      {model.is_active ? (
                        <span className="badge success">启用</span>
                      ) : (
                        <span className="badge rejected">停用</span>
                      )}
                    </td>
                    <td>
                      <div className="action-group">
                        <button type="button" className="secondary" onClick={() => handleTest(model)} disabled={actingId === model.id}>测试</button>
                        {!model.is_default && (
                          <button type="button" className="secondary" onClick={() => handleSetDefault(model)} disabled={actingId === model.id}>默认</button>
                        )}
                        <button type="button" className="secondary" onClick={() => handleToggle(model)} disabled={actingId === model.id}>
                          {model.is_active ? '停用' : '启用'}
                        </button>
                        <button type="button" className="secondary" onClick={() => openEdit(model)}>编辑</button>
                        <button type="button" className="danger" onClick={() => setDeleteTarget(model)} disabled={actingId === model.id || model.is_default}>删除</button>
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
          title={editing ? '编辑模型' : '添加模型'}
          onClose={() => setModalOpen(false)}
          footer={
            <>
              <button type="button" className="secondary" onClick={() => setModalOpen(false)}>取消</button>
              <button type="button" onClick={handleSave} disabled={submitting || !form.model_name || !form.display_name}>
                {submitting ? '保存中...' : '保存'}
              </button>
            </>
          }
        >
          <div className="form-group">
            <label htmlFor="model-provider">供应商</label>
            <select
              id="model-provider"
              value={form.provider}
              onChange={(e) => setForm({ ...form, provider: e.target.value, api_base: PROVIDER_DEFAULTS[e.target.value] || '' })}
            >
              {PROVIDERS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
            </select>
          </div>
          <div className="form-group">
            <label htmlFor="model-name">模型名称</label>
            <input id="model-name" value={form.model_name} onChange={(e) => setForm({ ...form, model_name: e.target.value })} placeholder="如 gpt-4o、qwen2.5:7b" />
          </div>
          <div className="form-group">
            <label htmlFor="model-display">展示名称</label>
            <input id="model-display" value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} placeholder="便于识别的名称" />
          </div>
          <div className="form-group">
            <label htmlFor="model-apibase">API 地址</label>
            <input id="model-apibase" value={form.api_base} onChange={(e) => setForm({ ...form, api_base: e.target.value })} />
          </div>
          <div className="form-group">
            <label htmlFor="model-key">API Key {editing && <span className="text-muted text-sm">（留空不修改）</span>}</label>
            <input id="model-key" type="password" value={form.api_key} onChange={(e) => setForm({ ...form, api_key: e.target.value })} />
          </div>
          <div className="form-row" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1rem' }}>
            <div className="form-group">
              <label htmlFor="model-temp">Temperature</label>
              <input id="model-temp" type="number" step="0.1" min="0" max="2" value={form.temperature} onChange={(e) => setForm({ ...form, temperature: parseFloat(e.target.value) || 0.7 })} />
            </div>
            <div className="form-group">
              <label htmlFor="model-tokens">Max Tokens</label>
              <input id="model-tokens" type="number" min="1" value={form.max_tokens} onChange={(e) => setForm({ ...form, max_tokens: parseInt(e.target.value) || 4096 })} />
            </div>
            <div className="form-group">
              <label htmlFor="model-topp">Top P</label>
              <input id="model-topp" type="number" step="0.05" min="0" max="1" value={form.top_p} onChange={(e) => setForm({ ...form, top_p: parseFloat(e.target.value) || 0.9 })} />
            </div>
          </div>
          <div className="form-group">
            <label><input type="checkbox" checked={form.is_default} onChange={(e) => setForm({ ...form, is_default: e.target.checked })} /> 设为默认模型</label>
          </div>
          <div className="form-group">
            <label><input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} /> 启用</label>
          </div>
        </Modal>
      )}

      <ConfirmDialog
        open={!!deleteTarget}
        title="确认删除"
        message={deleteTarget ? <>确定要删除模型「<strong>{deleteTarget.display_name}</strong>」吗？</> : null}
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
