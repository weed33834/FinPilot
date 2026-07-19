import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
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

const TYPE_LABELS: Record<string, string> = {
  chat: '对话',
  analysis: '分析',
  report: '报告',
  sql_agent: 'SQL',
}

const formSchema = z.object({
  name: z.string().min(1, '必填'),
  description: z.string().optional(),
  agent_type: z.string().min(1, '必填'),
  model_id: z.string().optional(),
  prompt_id: z.string().optional(),
  system_prompt: z.string().optional(),
  max_iterations: z.number().min(1).max(100).default(10),
  temperature: z.number().min(0).max(2).default(0.7),
  tool_ids: z.array(z.string()).default([]),
  skill_ids: z.array(z.string()).default([]),
})

type FormValues = z.infer<typeof formSchema>

interface SelectOption {
  id: string
  name?: string
  model_name?: string
  display_name?: string
  label?: string
}

export default function AgentConfigManagement() {
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [formOpen, setFormOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [testOpen, setTestOpen] = useState(false)
  const [testTarget, setTestTarget] = useState<AgentConfigItem | null>(null)
  const [testMessage, setTestMessage] = useState('你好，请介绍一下你自己')
  const [testResult, setTestResult] = useState<AgentTestResult | null>(null)
  const [testLoading, setTestLoading] = useState(false)
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null)

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

  const { data: listData, isLoading } = useQuery({
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

  return (
    <div style={{ padding: 24 }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0 }}>Agent 配置管理</h1>
        <button onClick={openCreate} style={btnPrimaryStyle}>
          + 创建 Agent
        </button>
      </div>

      {/* Filters */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
        <input
          placeholder="搜索名称或描述..."
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1) }}
          style={inputStyle}
        />
        <select value={typeFilter} onChange={(e) => { setTypeFilter(e.target.value); setPage(1) }} style={selectStyle}>
          <option value="">全部类型</option>
          <option value="chat">对话</option>
          <option value="analysis">分析</option>
          <option value="report">报告</option>
          <option value="sql_agent">SQL</option>
        </select>
        <select value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); setPage(1) }} style={selectStyle}>
          <option value="">全部状态</option>
          <option value="active">已启用</option>
          <option value="inactive">已禁用</option>
        </select>
      </div>

      {/* Table */}
      <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #e5e7eb', overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ background: '#f9fafb', borderBottom: '1px solid #e5e7eb' }}>
              {['名称', '类型', '关联模型', '关联提示词', '工具', '技能', '状态', '操作'].map((h) => (
                <th key={h} style={{ padding: '10px 12px', textAlign: 'left', fontSize: 13, color: '#6b7280', fontWeight: 600 }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={8} style={{ textAlign: 'center', padding: 40 }}>加载中...</td>
              </tr>
            ) : listData?.items.length === 0 ? (
              <tr>
                <td colSpan={8} style={{ textAlign: 'center', padding: 40, color: '#9ca3af' }}>暂无 Agent 配置</td>
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
                      {TYPE_LABELS[item.agent_type] || item.agent_type}
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
                        {item.is_active ? '启用' : '禁用'}
                      </span>
                    </label>
                  </td>
                  <td style={{ padding: '10px 12px' }}>
                    <div style={{ display: 'flex', gap: 4 }}>
                      <button onClick={() => { setTestTarget(item); setTestOpen(true); setTestResult(null) }} style={btnSmallStyle} title="测试">
                        <ICONS.send size={14} />
                      </button>
                      <button onClick={() => duplicateMut.mutate(item.id)} style={btnSmallStyle} title="复制">
                        <ICONS.copy size={14} />
                      </button>
                      <button onClick={() => openEdit(item)} style={btnSmallStyle} title="编辑">
                        <ICONS.reports size={14} />
                      </button>
                      <button onClick={() => setDeleteConfirmId(item.id)} style={{ ...btnSmallStyle, color: '#ef4444' }} title="删除">
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
            <span style={{ fontSize: 13, color: '#6b7280' }}>共 {listData.total} 条</span>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                style={{ ...btnSmallStyle, opacity: page <= 1 ? 0.5 : 1 }}
              >
                上一页
              </button>
              <span style={{ fontSize: 13, padding: '4px 8px' }}>第 {page} 页</span>
              <button
                onClick={() => setPage((p) => p + 1)}
                disabled={page * 20 >= listData.total}
                style={{ ...btnSmallStyle, opacity: page * 20 >= listData.total ? 0.5 : 1 }}
              >
                下一页
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
                {editingId ? '编辑 Agent 配置' : '创建 Agent 配置'}
              </h2>
              <button onClick={() => { setFormOpen(false); setEditingId(null) }} style={btnSmallStyle}>
                <ICONS.close size={18} />
              </button>
            </div>

            <form onSubmit={form.handleSubmit(onSubmit)}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                <div>
                  <label style={labelStyle}>名称 *</label>
                  <input {...form.register('name')} style={inputStyle} placeholder="Agent 名称" />
                  {form.formState.errors.name && <p style={errorStyle}>{form.formState.errors.name.message}</p>}
                </div>
                <div>
                  <label style={labelStyle}>类型 *</label>
                  <select {...form.register('agent_type')} style={selectStyle}>
                    <option value="chat">对话 Agent</option>
                    <option value="analysis">分析 Agent</option>
                    <option value="report">报告 Agent</option>
                    <option value="sql_agent">SQL Agent</option>
                  </select>
                </div>
                <div>
                  <label style={labelStyle}>描述</label>
                  <input {...form.register('description')} style={inputStyle} placeholder="描述" />
                </div>
                <div>
                  <label style={labelStyle}>关联模型</label>
                  <select {...form.register('model_id')} style={selectStyle}>
                    <option value="">不关联</option>
                    {(modelsData ?? []).map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.model_name || m.name || m.id}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label style={labelStyle}>关联提示词模板</label>
                  <select {...form.register('prompt_id')} style={selectStyle}>
                    <option value="">不关联</option>
                    {(promptsData ?? []).map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name || p.id}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label style={labelStyle}>最大迭代次数</label>
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
                  Temperature: {form.watch('temperature').toFixed(1)}
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
                <label style={labelStyle}>System Prompt</label>
                <textarea
                  {...form.register('system_prompt')}
                  style={{ ...inputStyle, minHeight: 120, fontFamily: 'monospace', fontSize: 13 }}
                  placeholder="覆盖默认 system prompt（可选）"
                  rows={6}
                />
              </div>

              {/* Tool select multi */}
              <div style={{ marginTop: 16 }}>
                <label style={labelStyle}>关联工具 (多选)</label>
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
                    {(toolsData ?? []).map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.display_name || t.name || t.id}
                      </option>
                    ))}
                  </select>
                </div>
                <p style={{ fontSize: 12, color: '#9ca3af', marginTop: 4 }}>
                  按住 Ctrl 多选
                </p>
              </div>

              {/* Skill select multi */}
              <div style={{ marginTop: 16 }}>
                <label style={labelStyle}>关联技能 (多选)</label>
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
                  按住 Ctrl 多选
                </p>
              </div>

              {/* Error */}
              {(createMut.error || updateMut.error) && (
                <p style={errorStyle}>
                  {getErrorMessage(createMut.error || updateMut.error)}
                </p>
              )}

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 24 }}>
                <button
                  type="button"
                  onClick={() => { setFormOpen(false); setEditingId(null) }}
                  style={btnSecondaryStyle}
                >
                  取消
                </button>
                <button type="submit" disabled={isMutating} style={btnPrimaryStyle}>
                  {isMutating ? '保存中...' : editingId ? '保存' : '创建'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Test Dialog */}
      {testOpen && testTarget && (
        <div style={overlayStyle} onClick={() => setTestOpen(false)}>
          <div style={dialogStyle} onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <h2 style={{ fontSize: 18, fontWeight: 600, margin: 0 }}>测试: {testTarget.name}</h2>
              <button onClick={() => setTestOpen(false)} style={btnSmallStyle}><ICONS.close size={18} /></button>
            </div>

            <label style={labelStyle}>测试消息</label>
            <input
              value={testMessage}
              onChange={(e) => setTestMessage(e.target.value)}
              style={inputStyle}
              placeholder="输入测试消息..."
            />

            <button
              onClick={handleTest}
              disabled={testLoading}
              style={{ ...btnPrimaryStyle, marginTop: 12 }}
            >
              {testLoading ? '测试中...' : '发送测试'}
            </button>

            {testResult && (
              <div style={{
                marginTop: 16,
                padding: 12,
                borderRadius: 8,
                background: testResult.success ? '#f0fdf4' : '#fef2f2',
                border: `1px solid ${testResult.success ? '#bbf7d0' : '#fecaca'}`,
              }}>
                <p style={{ fontSize: 13, fontWeight: 600, color: testResult.success ? '#166534' : '#991b1b' }}>
                  {testResult.message}
                </p>
                {testResult.thinking && (
                  <div style={{ marginTop: 8, fontSize: 12, color: '#6b7280' }}>
                    <strong>思考:</strong> {testResult.thinking}
                  </div>
                )}
                {testResult.answer && (
                  <div style={{ marginTop: 8, fontSize: 13, whiteSpace: 'pre-wrap' }}>
                    <strong>回答:</strong> {testResult.answer}
                  </div>
                )}
                {testResult.execution_time_ms > 0 && (
                  <div style={{ marginTop: 8, fontSize: 12, color: '#9ca3af' }}>
                    耗时: {testResult.execution_time_ms}ms
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Delete Confirm */}
      {deleteConfirmId && (
        <div style={overlayStyle} onClick={() => setDeleteConfirmId(null)}>
          <div style={dialogStyle} onClick={(e) => e.stopPropagation()}>
            <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 12 }}>确认删除</h2>
            <p style={{ color: '#6b7280', marginBottom: 20 }}>确定要删除此 Agent 配置吗？此操作不可撤销。</p>
            {deleteMut.error && (
              <p style={errorStyle}>{getErrorMessage(deleteMut.error)}</p>
            )}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
              <button onClick={() => setDeleteConfirmId(null)} style={btnSecondaryStyle}>取消</button>
              <button
                onClick={() => deleteMut.mutate(deleteConfirmId)}
                disabled={deleteMut.isPending}
                style={{ ...btnPrimaryStyle, background: '#ef4444' }}
              >
                {deleteMut.isPending ? '删除中...' : '确认删除'}
              </button>
            </div>
          </div>
        </div>
      )}
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
