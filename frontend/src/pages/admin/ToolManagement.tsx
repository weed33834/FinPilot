import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { ICONS } from '../../components/ui/Icons.tsx'
import { getErrorMessage } from '../../utils/errors.ts'
import {
  listTools,
  listToolTypes,
  createTool,
  updateTool,
  deleteTool,
  toggleTool,
  testTool,
  duplicateTool,
  type ToolItem,
  type ToolTypeOption,
  type ToolCreatePayload,
  type ToolUpdatePayload,
} from '../../api/tools.ts'

const TYPE_BADGES: Record<string, string> = {
  python_function: 'bg-blue-900/40 text-blue-300 border-blue-700',
  http_api: 'bg-green-900/40 text-green-300 border-green-700',
  sql_query: 'bg-purple-900/40 text-purple-300 border-purple-700',
  file_operation: 'bg-amber-900/40 text-amber-300 border-amber-700',
  search: 'bg-cyan-900/40 text-cyan-300 border-cyan-700',
  web_search: 'bg-rose-900/40 text-rose-300 border-rose-700',
}

const TYPE_LABELS: Record<string, string> = {
  python_function: 'Python 函数',
  http_api: 'HTTP API',
  sql_query: 'SQL 查询',
  file_operation: '文件操作',
  search: '搜索',
  web_search: '网络搜索',
}

const formSchema = z.object({
  name: z.string().min(1, '必填'),
  display_name: z.string().min(1, '必填'),
  description: z.string().optional(),
  type: z.string().min(1, '必填'),
  config: z.record(z.string(), z.unknown()).optional(),
  api_key: z.string().optional(),
})

type FormValues = z.infer<typeof formSchema>

export default function ToolManagement() {
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [formOpen, setFormOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [testOpen, setTestOpen] = useState(false)
  const [testTarget, setTestTarget] = useState<ToolItem | null>(null)
  const [testParams, setTestParams] = useState('{}')
  const [testResult, setTestResult] = useState<{
    success: boolean
    message: string
    result: string | null
    execution_time_ms: number
  } | null>(null)
  const [testLoading, setTestLoading] = useState(false)
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null)

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema) as any,
    defaultValues: {
      name: '',
      display_name: '',
      description: '',
      type: '',
      config: {},
      api_key: '',
    },
  })

  const { data: toolsData, isLoading } = useQuery({
    queryKey: ['admin-tools', page, search, typeFilter, statusFilter],
    queryFn: () =>
      listTools({
        page,
        page_size: 15,
        search: search || '',
        type: typeFilter || '',
        is_active: statusFilter || '',
      }),
  })

  const { data: typeOptions } = useQuery({
    queryKey: ['admin-tool-types'],
    queryFn: listToolTypes,
  })

  const createMut = useMutation({
    mutationFn: (payload: ToolCreatePayload) => createTool(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-tools'] })
      setFormOpen(false)
    },
    onError: (err: unknown) => alert(`创建失败: ${getErrorMessage(err)}`),
  })

  const updateMut = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: ToolUpdatePayload }) =>
      updateTool(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-tools'] })
      setFormOpen(false)
      setEditingId(null)
    },
    onError: (err: unknown) => alert(`更新失败: ${getErrorMessage(err)}`),
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteTool(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-tools'] })
      setDeleteConfirmId(null)
    },
    onError: (err: unknown) => alert(`删除失败: ${getErrorMessage(err)}`),
  })

  const toggleMut = useMutation({
    mutationFn: (id: string) => toggleTool(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-tools'] })
    },
    onError: (err: unknown) => alert(`操作失败: ${getErrorMessage(err)}`),
  })

  const duplicateMut = useMutation({
    mutationFn: (id: string) => duplicateTool(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-tools'] })
    },
    onError: (err: unknown) => alert(`复制失败: ${getErrorMessage(err)}`),
  })

  const handleCreate = () => {
    setEditingId(null)
    form.reset({
      name: '',
      display_name: '',
      description: '',
      type: '',
      config: {},
      api_key: '',
    })
    setFormOpen(true)
  }

  const handleEdit = (tool: ToolItem) => {
    setEditingId(tool.id)
    form.reset({
      name: tool.name,
      display_name: tool.display_name,
      description: tool.description || '',
      type: tool.type,
      config: tool.config || {},
      api_key: '',
    })
    setFormOpen(true)
  }

  const handleSave = form.handleSubmit((values) => {
    const payload = {
      name: values.name,
      display_name: values.display_name,
      description: values.description,
      type: values.type,
      config: values.config || {},
      api_key: values.api_key || undefined,
    }

    if (editingId) {
      updateMut.mutate({ id: editingId, payload })
    } else {
      createMut.mutate(payload)
    }
  })

  const handleTest = async () => {
    if (!testTarget) return
    setTestLoading(true)
    setTestResult(null)
    try {
      let params: Record<string, unknown> = {}
      try {
        params = JSON.parse(testParams)
      } catch {
        params = {}
      }
      const res = await testTool(testTarget.id, { parameters: params })
      setTestResult(res.data.data)
    } catch (err: unknown) {
      setTestResult({
        success: false,
        message: getErrorMessage(err),
        result: null,
        execution_time_ms: 0,
      })
    } finally {
      setTestLoading(false)
    }
  }

  const items: ToolItem[] = toolsData?.data?.data?.items ?? []
  const total = toolsData?.data?.data?.total ?? 0
  const pageSize = toolsData?.data?.data?.page_size ?? 15
  const totalPages = Math.ceil(total / pageSize)

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-white">工具管理</h2>
        <button
          onClick={handleCreate}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 transition-colors"
        >
          + 创建工具
        </button>
      </div>

      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-3">
        <input
          type="text"
          placeholder="搜索工具名..."
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1) }}
          className="w-56 rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white placeholder-slate-400 focus:border-blue-500 focus:outline-none"
        />
        <select
          value={typeFilter}
          onChange={(e) => { setTypeFilter(e.target.value); setPage(1) }}
          className="rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
        >
          <option value="">所有类型</option>
          {typeOptions?.data?.data?.map((t: ToolTypeOption) => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </select>
        <select
          value={statusFilter}
          onChange={(e) => { setStatusFilter(e.target.value); setPage(1) }}
          className="rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
        >
          <option value="">所有状态</option>
          <option value="active">已启用</option>
          <option value="inactive">已禁用</option>
        </select>
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="flex items-center justify-center py-20 text-slate-400">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-blue-500 border-t-transparent mr-2" />
          加载中...
        </div>
      ) : items.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-slate-400">
          <ICONS.empty size={48} className="mb-3 opacity-40" />
          <p>暂无工具数据</p>
          <p className="text-sm mt-1">点击"创建工具"添加</p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-slate-700/50">
          <table className="w-full text-sm">
            <thead className="bg-slate-800/60 text-left text-slate-300">
              <tr>
                <th className="px-4 py-3 font-medium">展示名</th>
                <th className="px-4 py-3 font-medium">类型</th>
                <th className="px-4 py-3 font-medium">内置</th>
                <th className="px-4 py-3 font-medium">状态</th>
                <th className="px-4 py-3 font-medium">简介</th>
                <th className="px-4 py-3 font-medium">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700/30">
              {items.map((tool) => (
                <tr key={tool.id} className="hover:bg-slate-800/30 transition-colors">
                  <td className="px-4 py-3 font-medium text-white">{tool.display_name}</td>
                  <td className="px-4 py-3">
                    <span className={`rounded border px-2 py-0.5 text-xs ${TYPE_BADGES[tool.type] || 'bg-slate-700 text-slate-300 border-slate-600'}`}>
                      {TYPE_LABELS[tool.type] || tool.type}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {tool.is_builtin ? (
                      <span className="rounded bg-slate-700/50 text-slate-400 px-2 py-0.5 text-xs">内置</span>
                    ) : (
                      <span className="rounded bg-indigo-900/30 text-indigo-300 px-2 py-0.5 text-xs">自定义</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => toggleMut.mutate(tool.id)}
                      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                        tool.is_active ? 'bg-green-600' : 'bg-slate-600'
                      }`}
                    >
                      <span
                        className={`inline-block h-4 w-4 rounded-full bg-white transition-transform ${
                          tool.is_active ? 'translate-x-6' : 'translate-x-1'
                        }`}
                      />
                    </button>
                  </td>
                  <td className="px-4 py-3 text-slate-400 max-w-[200px] truncate">
                    {tool.description || '-'}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => { setTestTarget(tool); setTestParams('{}'); setTestResult(null); setTestOpen(true) }}
                        className="rounded p-1.5 text-slate-400 hover:bg-slate-700 hover:text-blue-400 transition-colors"
                        title="测试"
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12" /></svg>
                      </button>
                      <button
                        onClick={() => duplicateMut.mutate(tool.id)}
                        className="rounded p-1.5 text-slate-400 hover:bg-slate-700 hover:text-cyan-400 transition-colors"
                        title="复制"
                      >
                        <ICONS.copy size={14} />
                      </button>
                      <button
                        onClick={() => handleEdit(tool)}
                        className="rounded p-1.5 text-slate-400 hover:bg-slate-700 hover:text-amber-400 transition-colors"
                        title="编辑"
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" /><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" /></svg>
                      </button>
                      {!tool.is_builtin && (
                        <button
                          onClick={() => setDeleteConfirmId(tool.id)}
                          className="rounded p-1.5 text-slate-400 hover:bg-slate-700 hover:text-red-400 transition-colors"
                          title="删除"
                        >
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" /><line x1="10" y1="11" x2="10" y2="17" /><line x1="14" y1="11" x2="14" y2="17" /></svg>
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm text-slate-400">
          <span>共 {total} 个工具</span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
              className="rounded px-3 py-1 border border-slate-700 hover:bg-slate-800 disabled:opacity-40"
            >
              上一页
            </button>
            <span>第 {page}/{totalPages} 页</span>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
              className="rounded px-3 py-1 border border-slate-700 hover:bg-slate-800 disabled:opacity-40"
            >
              下一页
            </button>
          </div>
        </div>
      )}

      {/* Create/Edit Dialog */}
      {formOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="w-[900px] max-h-[85vh] overflow-y-auto rounded-xl border border-slate-700 bg-slate-900 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-700 px-6 py-4">
              <h3 className="text-lg font-semibold text-white">
                {editingId ? '编辑工具' : '创建工具'}
              </h3>
              <button
                onClick={() => { setFormOpen(false); setEditingId(null) }}
                className="text-slate-400 hover:text-white transition-colors"
              >
                <ICONS.close size={18} />
              </button>
            </div>
            <form onSubmit={handleSave} className="space-y-4 px-6 py-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1">工具名 (name)</label>
                  <input
                    {...form.register('name')}
                    disabled={editingId !== null}
                    className="w-full rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white disabled:opacity-50 focus:border-blue-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1">展示名</label>
                  <input
                    {...form.register('display_name')}
                    className="w-full rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1">类型</label>
                  <select
                    {...form.register('type')}
                    className="w-full rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
                  >
                    <option value="">选择类型</option>
                    {typeOptions?.data?.data?.map((t: ToolTypeOption) => (
                      <option key={t.value} value={t.value}>{t.label} — {t.description}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1">API Key（可选）</label>
                  <input
                    {...form.register('api_key')}
                    type="password"
                    className="w-full rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
                  />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">描述</label>
                <textarea
                  {...form.register('description')}
                  rows={3}
                  className="w-full rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">Config (JSON)</label>
                <textarea
                  value={JSON.stringify(form.watch('config') || {}, null, 2)}
                  onChange={(e) => {
                    try {
                      form.setValue('config', JSON.parse(e.target.value))
                    } catch {}
                  }}
                  rows={6}
                  className="w-full rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm font-mono text-white focus:border-blue-500 focus:outline-none"
                />
              </div>
              <div className="flex justify-end gap-3 border-t border-slate-700 pt-4">
                <button
                  type="button"
                  onClick={() => { setFormOpen(false); setEditingId(null) }}
                  className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-300 hover:bg-slate-800"
                >
                  取消
                </button>
                <button
                  type="submit"
                  disabled={createMut.isPending || updateMut.isPending}
                  className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 transition-colors"
                >
                  {editingId ? '保存' : '创建'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete Confirm Dialog */}
      {deleteConfirmId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="w-[400px] rounded-xl border border-slate-700 bg-slate-900 shadow-2xl p-6">
            <h3 className="text-lg font-semibold text-white mb-2">确认删除</h3>
            <p className="text-sm text-slate-400">此操作将从系统中移除该工具，不可恢复。确定要继续吗？</p>
            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={() => setDeleteConfirmId(null)}
                className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-300 hover:bg-slate-800"
              >
                取消
              </button>
              <button
                onClick={() => deleteMut.mutate(deleteConfirmId)}
                disabled={deleteMut.isPending}
                className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-500 transition-colors"
              >
                删除
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Test Dialog */}
      {testOpen && testTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="w-[600px] max-h-[80vh] overflow-y-auto rounded-xl border border-slate-700 bg-slate-900 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-700 px-6 py-4">
              <h3 className="text-lg font-semibold text-white">
                测试工具: {testTarget.display_name}
              </h3>
              <button onClick={() => setTestOpen(false)} className="text-slate-400 hover:text-white">
                <ICONS.close size={18} />
              </button>
            </div>
            <div className="space-y-4 px-6 py-4">
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">参数 (JSON)</label>
                <textarea
                  value={testParams}
                  onChange={(e) => setTestParams(e.target.value)}
                  rows={6}
                  className="w-full rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm font-mono text-white focus:border-blue-500 focus:outline-none"
                />
              </div>
              <button
                onClick={handleTest}
                disabled={testLoading}
                className="rounded-lg bg-cyan-600 px-4 py-2 text-sm font-medium text-white hover:bg-cyan-500 transition-colors"
              >
                {testLoading ? '测试中...' : '运行测试'}
              </button>
              {testResult && (
                <div className={`rounded-lg p-4 text-sm ${testResult.success ? 'bg-green-900/30 border border-green-700 text-green-300' : 'bg-red-900/30 border border-red-700 text-red-300'}`}>
                  <div className="font-medium mb-1">{testResult.success ? '成功' : '失败'}: {testResult.message}</div>
                  {testResult.result && (
                    <pre className="mt-2 whitespace-pre-wrap text-xs opacity-80">{testResult.result}</pre>
                  )}
                  {testResult.execution_time_ms > 0 && (
                    <div className="mt-2 text-xs opacity-60">耗时: {testResult.execution_time_ms}ms</div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
