import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { ICONS } from '../../components/ui/Icons.tsx'
import { getErrorMessage } from '../../utils/errors.ts'
import {
  listSearchEngines,
  createSearchEngine,
  updateSearchEngine,
  deleteSearchEngine,
  toggleSearchEngine,
  setDefaultEngine,
  testSearchEngine,
  type SearchEngineItem,
  type SearchEngineCreatePayload,
  type SearchEngineUpdatePayload,
} from '../../api/searchEngines.ts'

const ENGINE_BADGES: Record<string, string> = {
  google: 'bg-red-900/30 text-red-300 border-red-700',
  bing: 'bg-blue-900/30 text-blue-300 border-blue-700',
  duckduckgo: 'bg-amber-900/30 text-amber-300 border-amber-700',
  serpapi: 'bg-green-900/30 text-green-300 border-green-700',
  tavily: 'bg-purple-900/30 text-purple-300 border-purple-700',
  searxng: 'bg-cyan-900/30 text-cyan-300 border-cyan-700',
}

const ENGINE_TYPES = [
  { value: 'google', label: 'Google Custom Search' },
  { value: 'bing', label: 'Bing' },
  { value: 'duckduckgo', label: 'DuckDuckGo' },
  { value: 'serpapi', label: 'SerpAPI' },
  { value: 'tavily', label: 'Tavily' },
  { value: 'searxng', label: 'SearXNG' },
]

const formSchema = z.object({
  name: z.string().min(1, '必填'),
  engine_type: z.string().min(1, '必填'),
  api_base: z.string().nullable().optional(),
  api_key: z.string().nullable().optional(),
  extra_params: z.object({
    cx: z.string().optional(),
    region: z.string().optional(),
    safe_search: z.string().optional(),
    max_results: z.number().optional(),
  }).optional(),
  priority: z.coerce.number().min(0).default(0),
})

type FormValues = z.infer<typeof formSchema>

interface ExtraParamRow {
  key: string
  value: string
}

export default function SearchEngineManagement() {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [formOpen, setFormOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [extraRows, setExtraRows] = useState<ExtraParamRow[]>([])
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null)
  const [testOpen, setTestOpen] = useState(false)
  const [testTarget, setTestTarget] = useState<SearchEngineItem | null>(null)
  const [testQuery, setTestQuery] = useState('')
  const [testResult, setTestResult] = useState<{
    success: boolean
    message: string
    result_count: number | null
    first_snippet: string | null
  } | null>(null)
  const [testLoading, setTestLoading] = useState(false)

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema) as any,
    defaultValues: {
      name: '',
      engine_type: '',
      api_base: '',
      api_key: '',
      extra_params: { cx: '', region: '', safe_search: '', max_results: 10 },
      priority: 0,
    },
  })

  const { data: enginesData, isLoading } = useQuery({
    queryKey: ['admin-search-engines', search],
    queryFn: () => listSearchEngines().then((r) => r.data),
  })

  const createMut = useMutation({
    mutationFn: (payload: SearchEngineCreatePayload) => createSearchEngine(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-search-engines'] })
      setFormOpen(false)
    },
    onError: (err: unknown) => alert(`创建失败: ${getErrorMessage(err)}`),
  })

  const updateMut = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: SearchEngineUpdatePayload }) =>
      updateSearchEngine(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-search-engines'] })
      setFormOpen(false)
      setEditingId(null)
    },
    onError: (err: unknown) => alert(`更新失败: ${getErrorMessage(err)}`),
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteSearchEngine(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-search-engines'] })
      setDeleteConfirmId(null)
    },
    onError: (err: unknown) => alert(`删除失败: ${getErrorMessage(err)}`),
  })

  const toggleMut = useMutation({
    mutationFn: (id: string) => toggleSearchEngine(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin-search-engines'] }),
  })

  const setDefaultMut = useMutation({
    mutationFn: (id: string) => setDefaultEngine(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin-search-engines'] }),
    onError: (err: unknown) => alert(`操作失败: ${getErrorMessage(err)}`),
  })

  const handleCreate = () => {
    setEditingId(null)
    form.reset({
      name: '',
      engine_type: '',
      api_base: '',
      api_key: '',
      extra_params: { cx: '', region: '', safe_search: '', max_results: 10 },
      priority: 0,
    })
    setExtraRows([])
    setFormOpen(true)
  }

  const handleEdit = (engine: SearchEngineItem) => {
    setEditingId(engine.id)
    form.reset({
      name: engine.name,
      engine_type: engine.engine_type,
      api_base: engine.api_base || '',
      api_key: '',
      extra_params: engine.extra_params || { cx: '', region: '', safe_search: '', max_results: 10 },
      priority: engine.priority || 0,
    })
    // Convert extra_params to rows (excluding known keys)
    const knownKeys = ['cx', 'region', 'safe_search', 'max_results']
    const customRows: ExtraParamRow[] = []
    if (engine.extra_params) {
      for (const [key, value] of Object.entries(engine.extra_params)) {
        if (!knownKeys.includes(key)) {
          customRows.push({ key, value: String(value) })
        }
      }
    }
    setExtraRows(customRows)
    setFormOpen(true)
  }

  const handleSave = form.handleSubmit((values) => {
    // Merge extra_rows into extra_params
    const mergedExtra: Record<string, unknown> = { ...values.extra_params }
    for (const row of extraRows) {
      if (row.key.trim()) {
        mergedExtra[row.key.trim()] = row.value
      }
    }
    // Clean undefineds
    const cleanExtra: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(mergedExtra)) {
      if (v !== undefined && v !== '') cleanExtra[k] = v
    }

    const payload = {
      name: values.name,
      engine_type: values.engine_type,
      api_base: values.api_base || null,
      api_key: values.api_key || null,
      extra_params: cleanExtra,
      priority: values.priority,
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
      const res = await testSearchEngine(testTarget.id)
      setTestResult(res.data.data)
    } catch (err: unknown) {
      setTestResult({ success: false, message: getErrorMessage(err), result_count: null, first_snippet: null })
    } finally {
      setTestLoading(false)
    }
  }

  const items: SearchEngineItem[] = enginesData?.data ?? []

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-white">搜索引擎管理</h2>
        <button
          onClick={handleCreate}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 transition-colors"
        >
          + 添加搜索引擎
        </button>
      </div>

      {/* Toolbar */}
      <div className="flex items-center gap-3">
        <input
          type="text"
          placeholder="搜索..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-56 rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white placeholder-slate-400 focus:border-blue-500 focus:outline-none"
        />
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
          <p>暂无搜索引擎配置</p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-slate-700/50">
          <table className="w-full text-sm">
            <thead className="bg-slate-800/60 text-left text-slate-300">
              <tr>
                <th className="px-4 py-3 font-medium">名称</th>
                <th className="px-4 py-3 font-medium">类型</th>
                <th className="px-4 py-3 font-medium">API Base</th>
                <th className="px-4 py-3 font-medium">默认</th>
                <th className="px-4 py-3 font-medium">优先级</th>
                <th className="px-4 py-3 font-medium">状态</th>
                <th className="px-4 py-3 font-medium">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700/30">
              {items.map((engine) => (
                <tr key={engine.id} className="hover:bg-slate-800/30 transition-colors">
                  <td className="px-4 py-3 font-medium text-white">{engine.name}</td>
                  <td className="px-4 py-3">
                    <span className={`rounded border px-2 py-0.5 text-xs ${ENGINE_BADGES[engine.engine_type] || 'bg-slate-700 text-slate-300 border-slate-600'}`}>
                      {engine.engine_type}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-400 max-w-[200px] truncate">
                    {engine.api_base || '-'}
                  </td>
                  <td className="px-4 py-3">
                    {engine.is_default ? (
                      <span className="text-yellow-400" title="默认搜索引擎">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                          <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
                        </svg>
                      </span>
                    ) : (
                      <button
                        onClick={() => setDefaultMut.mutate(engine.id)}
                        className="text-slate-600 hover:text-yellow-400 transition-colors"
                        title="设为默认"
                      >
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
                        </svg>
                      </button>
                    )}
                  </td>
                  <td className="px-4 py-3 text-slate-400">{engine.priority || 0}</td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => toggleMut.mutate(engine.id)}
                      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                        engine.is_active ? 'bg-green-600' : 'bg-slate-600'
                      }`}
                    >
                      <span
                        className={`inline-block h-4 w-4 rounded-full bg-white transition-transform ${
                          engine.is_active ? 'translate-x-6' : 'translate-x-1'
                        }`}
                      />
                    </button>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => { setTestTarget(engine); setTestQuery(''); setTestResult(null); setTestOpen(true) }}
                        className="rounded p-1.5 text-slate-400 hover:bg-slate-700 hover:text-blue-400 transition-colors"
                        title="测试搜索"
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12" /></svg>
                      </button>
                      <button
                        onClick={() => handleEdit(engine)}
                        className="rounded p-1.5 text-slate-400 hover:bg-slate-700 hover:text-amber-400 transition-colors"
                        title="编辑"
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" /><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" /></svg>
                      </button>
                      <button
                        onClick={() => setDeleteConfirmId(engine.id)}
                        className="rounded p-1.5 text-slate-400 hover:bg-slate-700 hover:text-red-400 transition-colors"
                        title="删除"
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" /><line x1="10" y1="11" x2="10" y2="17" /><line x1="14" y1="11" x2="14" y2="17" /></svg>
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Create/Edit Dialog */}
      {formOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="w-[600px] max-h-[85vh] overflow-y-auto rounded-xl border border-slate-700 bg-slate-900 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-700 px-6 py-4">
              <h3 className="text-lg font-semibold text-white">
                {editingId ? '编辑搜索引擎' : '添加搜索引擎'}
              </h3>
              <button onClick={() => { setFormOpen(false); setEditingId(null) }} className="text-slate-400 hover:text-white">
                <ICONS.close size={18} />
              </button>
            </div>
            <form onSubmit={handleSave} className="space-y-4 px-6 py-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1">名称</label>
                  <input
                    {...form.register('name')}
                    className="w-full rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1">引擎类型</label>
                  <select
                    {...form.register('engine_type')}
                    className="w-full rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
                  >
                    <option value="">选择类型</option>
                    {ENGINE_TYPES.map((t) => (
                      <option key={t.value} value={t.value}>{t.label}</option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1">API Base</label>
                  <input
                    {...form.register('api_base')}
                    className="w-full rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1">API Key</label>
                  <input
                    {...form.register('api_key')}
                    type="password"
                    className="w-full rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
                  />
                </div>
              </div>

              {/* Extra Params */}
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">内置参数</label>
                <div className="grid grid-cols-2 gap-3 mb-3">
                  <div>
                    <label className="text-xs text-slate-400">CX (Google)</label>
                    <input
                      {...form.register('extra_params.cx')}
                      className="w-full rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-slate-400">Region</label>
                    <input
                      {...form.register('extra_params.region')}
                      className="w-full rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-slate-400">Safe Search</label>
                    <select
                      {...form.register('extra_params.safe_search')}
                      className="w-full rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
                    >
                      <option value="">默认</option>
                      <option value="off">Off</option>
                      <option value="medium">Medium</option>
                      <option value="high">High</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-xs text-slate-400">Max Results</label>
                    <input
                      {...form.register('extra_params.max_results', { valueAsNumber: true })}
                      type="range"
                      min={1}
                      max={100}
                      className="w-full mt-1"
                    />
                    <span className="text-xs text-slate-400">{form.watch('extra_params.max_results') || 10}</span>
                  </div>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">优先级</label>
                <input
                  {...form.register('priority', { valueAsNumber: true })}
                  type="number"
                  min={0}
                  className="w-24 rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
                />
              </div>

              {/* Custom Extra Params KV Editor */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-sm font-medium text-slate-300">自定义额外参数</label>
                  <button
                    type="button"
                    onClick={() => setExtraRows([...extraRows, { key: '', value: '' }])}
                    className="rounded px-2 py-1 text-xs text-blue-400 hover:bg-slate-800"
                  >
                    + 添加参数
                  </button>
                </div>
                {extraRows.map((row, idx) => (
                  <div key={idx} className="flex items-center gap-3 mb-2">
                    <input
                      value={row.key}
                      onChange={(e) => {
                        const updated = [...extraRows]
                        updated[idx] = { ...row, key: e.target.value }
                        setExtraRows(updated)
                      }}
                      placeholder="Key"
                      className="w-1/3 rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-1.5 text-sm text-white focus:border-blue-500 focus:outline-none"
                    />
                    <input
                      value={row.value}
                      onChange={(e) => {
                        const updated = [...extraRows]
                        updated[idx] = { ...row, value: e.target.value }
                        setExtraRows(updated)
                      }}
                      placeholder="Value"
                      className="flex-1 rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-1.5 text-sm text-white focus:border-blue-500 focus:outline-none"
                    />
                    <button
                      type="button"
                      onClick={() => {
                        setExtraRows(extraRows.filter((_, i) => i !== idx))
                      }}
                      className="rounded p-1 text-slate-400 hover:text-red-400"
                    >
                      <ICONS.close size={14} />
                    </button>
                  </div>
                ))}
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
            <p className="text-sm text-slate-400">此操作将移除该搜索引擎配置，不可恢复。</p>
            <div className="flex justify-end gap-3 mt-6">
              <button onClick={() => setDeleteConfirmId(null)} className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-300 hover:bg-slate-800">
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
          <div className="w-[500px] rounded-xl border border-slate-700 bg-slate-900 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-700 px-6 py-4">
              <h3 className="text-lg font-semibold text-white">
                测试搜索: {testTarget.name}
              </h3>
              <button onClick={() => setTestOpen(false)} className="text-slate-400 hover:text-white">
                <ICONS.close size={18} />
              </button>
            </div>
            <div className="space-y-4 px-6 py-4">
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">搜索查询</label>
                <input
                  value={testQuery}
                  onChange={(e) => setTestQuery(e.target.value)}
                  placeholder="输入测试查询..."
                  className="w-full rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
                />
              </div>
              <button
                onClick={handleTest}
                disabled={testLoading}
                className="rounded-lg bg-cyan-600 px-4 py-2 text-sm font-medium text-white hover:bg-cyan-500 transition-colors"
              >
                {testLoading ? '搜索中...' : '测试搜索'}
              </button>
              {testResult && (
                <div className={`rounded-lg p-4 text-sm ${testResult.success ? 'bg-green-900/30 border border-green-700 text-green-300' : 'bg-red-900/30 border border-red-700 text-red-300'}`}>
                  <div className="font-medium mb-1">{testResult.success ? '成功' : '失败'}: {testResult.message}</div>
                  {testResult.success && (
                    <div className="mt-1 text-xs opacity-80">返回 {testResult.result_count} 条结果</div>
                  )}
                  {testResult.first_snippet && (
                    <pre className="mt-2 whitespace-pre-wrap text-xs opacity-80 max-h-40 overflow-y-auto">{testResult.first_snippet}</pre>
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

