import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { ICONS } from '../../components/ui/Icons.tsx'
import { getErrorMessage } from '../../utils/errors.ts'
import {
  listSkills,
  listSkillCategories,
  createSkill,
  updateSkill,
  deleteSkill,
  toggleSkill,
  testSkill,
  type SkillItem,
  type SkillCreatePayload,
  type SkillUpdatePayload,
} from '../../api/skills.ts'
import { listTools, type ToolItem } from '../../api/tools.ts'
import { listPrompts, type PromptTemplateItem } from '../../api/prompts.ts'

const formSchema = z.object({
  name: z.string().min(1, '必填'),
  display_name: z.string().min(1, '必填'),
  description: z.string().optional(),
  category: z.string().optional(),
  prompt_id: z.string().nullable().optional(),
  system_prompt_override: z.string().nullable().optional(),
  icon: z.string().nullable().optional(),
  tool_ids: z.array(z.string()).optional(),
})

type FormValues = z.infer<typeof formSchema>

export default function SkillManagement() {
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [formOpen, setFormOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [testOpen, setTestOpen] = useState(false)
  const [testTarget, setTestTarget] = useState<SkillItem | null>(null)
  const [testQuery, setTestQuery] = useState('')
  const [testResult, setTestResult] = useState<{
    success: boolean
    message: string
    result: string | null
  } | null>(null)
  const [testLoading, setTestLoading] = useState(false)
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null)

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema) as any,
    defaultValues: {
      name: '',
      display_name: '',
      description: '',
      category: '',
      prompt_id: null,
      system_prompt_override: '',
      icon: '',
      tool_ids: [],
    },
  })

  const { data: skillsData, isLoading } = useQuery({
    queryKey: ['admin-skills', page, search, categoryFilter, statusFilter],
    queryFn: () =>
      listSkills({
        page,
        page_size: 15,
        search: search || '',
        category: categoryFilter || '',
        is_active: statusFilter || '',
      }),
  })

  const { data: categoriesData } = useQuery({
    queryKey: ['admin-skill-categories'],
    queryFn: listSkillCategories,
  })

  const { data: toolsData } = useQuery({
    queryKey: ['admin-all-tools-list'],
    queryFn: () => listTools({ page: 1, page_size: 100 }),
  })

  const { data: promptsData } = useQuery({
    queryKey: ['admin-all-prompts-list'],
    queryFn: () => listPrompts({ page: 1, page_size: 100 }),
  })

  const createMut = useMutation({
    mutationFn: (payload: SkillCreatePayload) => createSkill(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-skills'] })
      setFormOpen(false)
    },
    onError: (err: unknown) => alert(`创建失败: ${getErrorMessage(err)}`),
  })

  const updateMut = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: SkillUpdatePayload }) =>
      updateSkill(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-skills'] })
      setFormOpen(false)
      setEditingId(null)
    },
    onError: (err: unknown) => alert(`更新失败: ${getErrorMessage(err)}`),
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteSkill(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-skills'] })
      setDeleteConfirmId(null)
    },
    onError: (err: unknown) => alert(`删除失败: ${getErrorMessage(err)}`),
  })

  const toggleMut = useMutation({
    mutationFn: (id: string) => toggleSkill(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-skills'] })
    },
  })

  const handleCreate = () => {
    setEditingId(null)
    form.reset({
      name: '',
      display_name: '',
      description: '',
      category: '',
      prompt_id: null,
      system_prompt_override: '',
      icon: '',
      tool_ids: [],
    })
    setFormOpen(true)
  }

  const handleEdit = (skill: SkillItem) => {
    setEditingId(skill.id)
    form.reset({
      name: skill.name,
      display_name: skill.display_name,
      description: skill.description || '',
      category: skill.category || '',
      prompt_id: skill.prompt_id,
      system_prompt_override: skill.system_prompt_override || '',
      icon: skill.icon || '',
      tool_ids: skill.tool_ids || [],
    })
    setFormOpen(true)
  }

  const handleSave = form.handleSubmit((values) => {
    const payload = {
      name: values.name,
      display_name: values.display_name,
      description: values.description,
      category: values.category || '',
      prompt_id: values.prompt_id,
      system_prompt_override: values.system_prompt_override || null,
      icon: values.icon || null,
      tool_ids: values.tool_ids,
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
      const res = await testSkill(testTarget.id, testQuery || 'test')
      setTestResult(res.data.data)
    } catch (err: unknown) {
      setTestResult({ success: false, message: getErrorMessage(err), result: null })
    } finally {
      setTestLoading(false)
    }
  }

  const selectedToolIds: string[] = (form.watch('tool_ids') as string[]) || []
  const allTools: ToolItem[] = toolsData?.data?.data?.items ?? []
  const availableTools = allTools.filter((t) => !selectedToolIds.includes(t.id))
  const selectedTools = allTools.filter((t) => selectedToolIds.includes(t.id))
  const allPrompts: PromptTemplateItem[] = promptsData?.data?.data?.items ?? []

  const items: SkillItem[] = skillsData?.data?.data?.items ?? []
  const total = skillsData?.data?.data?.total ?? 0
  const pageSize = skillsData?.data?.data?.page_size ?? 15
  const totalPages = Math.ceil(total / pageSize)

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-white">技能管理</h2>
        <button
          onClick={handleCreate}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 transition-colors"
        >
          + 创建技能
        </button>
      </div>

      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-3">
        <input
          type="text"
          placeholder="搜索技能名..."
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1) }}
          className="w-56 rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white placeholder-slate-400 focus:border-blue-500 focus:outline-none"
        />
        <select
          value={categoryFilter}
          onChange={(e) => { setCategoryFilter(e.target.value); setPage(1) }}
          className="rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
        >
          <option value="">所有分类</option>
          {categoriesData?.data?.data?.map((c: string) => (
            <option key={c} value={c}>{c}</option>
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
          <p>暂无技能数据</p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-slate-700/50">
          <table className="w-full text-sm">
            <thead className="bg-slate-800/60 text-left text-slate-300">
              <tr>
                <th className="px-4 py-3 font-medium">展示名</th>
                <th className="px-4 py-3 font-medium">分类</th>
                <th className="px-4 py-3 font-medium">关联工具</th>
                <th className="px-4 py-3 font-medium">Prompt</th>
                <th className="px-4 py-3 font-medium">状态</th>
                <th className="px-4 py-3 font-medium">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700/30">
              {items.map((skill) => (
                <tr key={skill.id} className="hover:bg-slate-800/30 transition-colors">
                  <td className="px-4 py-3 font-medium text-white">{skill.display_name}</td>
                  <td className="px-4 py-3">
                    {skill.category ? (
                      <span className="rounded bg-purple-900/30 text-purple-300 border border-purple-700/50 px-2 py-0.5 text-xs">
                        {skill.category}
                      </span>
                    ) : '-'}
                  </td>
                  <td className="px-4 py-3 text-slate-400">
                    {skill.tool_ids?.length || 0} 个工具
                  </td>
                  <td className="px-4 py-3 text-slate-400">
                    {skill.prompt_id ? `#${skill.prompt_id.slice(0, 8)}...` : '-'}
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => toggleMut.mutate(skill.id)}
                      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                        skill.is_active ? 'bg-green-600' : 'bg-slate-600'
                      }`}
                    >
                      <span
                        className={`inline-block h-4 w-4 rounded-full bg-white transition-transform ${
                          skill.is_active ? 'translate-x-6' : 'translate-x-1'
                        }`}
                      />
                    </button>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => { setTestTarget(skill); setTestQuery(''); setTestResult(null); setTestOpen(true) }}
                        className="rounded p-1.5 text-slate-400 hover:bg-slate-700 hover:text-blue-400 transition-colors"
                        title="测试"
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12" /></svg>
                      </button>
                      <button
                        onClick={() => handleEdit(skill)}
                        className="rounded p-1.5 text-slate-400 hover:bg-slate-700 hover:text-amber-400 transition-colors"
                        title="编辑"
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" /><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" /></svg>
                      </button>
                      <button
                        onClick={() => setDeleteConfirmId(skill.id)}
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

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm text-slate-400">
          <span>共 {total} 个技能</span>
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
          <div className="w-[800px] max-h-[85vh] overflow-y-auto rounded-xl border border-slate-700 bg-slate-900 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-700 px-6 py-4">
              <h3 className="text-lg font-semibold text-white">
                {editingId ? '编辑技能' : '创建技能'}
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
                  <label className="block text-sm font-medium text-slate-300 mb-1">技能名 (name)</label>
                  <input
                    {...form.register('name')}
                    className="w-full rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
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
              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1">分类</label>
                  <select
                    {...form.register('category')}
                    className="w-full rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
                  >
                    <option value="">无分类</option>
                    {categoriesData?.data?.data?.map((c: string) => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1">Prompt 模板</label>
                  <select
                    {...form.register('prompt_id')}
                    className="w-full rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
                  >
                    <option value="">无</option>
                    {allPrompts.map((p: PromptTemplateItem) => (
                      <option key={p.id} value={p.id}>{p.name}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1">图标</label>
                  <input
                    {...form.register('icon')}
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
                <label className="block text-sm font-medium text-slate-300 mb-1">System Prompt Override</label>
                <textarea
                  {...form.register('system_prompt_override')}
                  rows={4}
                  className="w-full rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm font-mono text-white focus:border-blue-500 focus:outline-none"
                />
              </div>

              {/* Tool Transfer (Shuttle) */}
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">关联工具</label>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <div className="text-xs text-slate-400 mb-1">可用工具</div>
                    <div className="h-40 overflow-y-auto rounded-lg border border-slate-700 bg-slate-800/50 p-2 space-y-1">
                      {availableTools.map((t) => (
                        <div
                          key={t.id}
                          className="flex items-center justify-between rounded px-2 py-1 hover:bg-slate-700/50 cursor-pointer text-sm text-slate-300"
                          onClick={() => {
                            form.setValue('tool_ids', [...selectedToolIds, t.id])
                          }}
                        >
                          <span>{t.display_name}</span>
                          <span className="text-xs text-slate-500">{TYPE_LABELS[t.type] || t.type}</span>
                        </div>
                      ))}
                      {availableTools.length === 0 && (
                        <div className="text-xs text-slate-500 p-2">无可用工具</div>
                      )}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-400 mb-1">已选工具</div>
                    <div className="h-40 overflow-y-auto rounded-lg border border-blue-700/50 bg-blue-900/10 p-2 space-y-1">
                      {selectedTools.map((t) => (
                        <div
                          key={t.id}
                          className="flex items-center justify-between rounded px-2 py-1 hover:bg-red-900/20 cursor-pointer text-sm text-blue-300"
                          onClick={() => {
                            form.setValue('tool_ids', selectedToolIds.filter((id) => id !== t.id))
                          }}
                        >
                          <span>{t.display_name}</span>
                          <span className="text-xs opacity-60">移除</span>
                        </div>
                      ))}
                      {selectedTools.length === 0 && (
                        <div className="text-xs text-slate-500 p-2">点击左侧添加</div>
                      )}
                    </div>
                  </div>
                </div>
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
            <p className="text-sm text-slate-400">此操作将从系统中移除该技能，不可恢复。确定要继续吗？</p>
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
          <div className="w-[500px] rounded-xl border border-slate-700 bg-slate-900 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-700 px-6 py-4">
              <h3 className="text-lg font-semibold text-white">
                测试技能: {testTarget.display_name}
              </h3>
              <button onClick={() => setTestOpen(false)} className="text-slate-400 hover:text-white">
                <ICONS.close size={18} />
              </button>
            </div>
            <div className="space-y-4 px-6 py-4">
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">测试查询</label>
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
                {testLoading ? '测试中...' : '运行测试'}
              </button>
              {testResult && (
                <div className={`rounded-lg p-4 text-sm ${testResult.success ? 'bg-green-900/30 border border-green-700 text-green-300' : 'bg-red-900/30 border border-red-700 text-red-300'}`}>
                  <div className="font-medium mb-1">{testResult.success ? '成功' : '失败'}: {testResult.message}</div>
                  {testResult.result && (
                    <pre className="mt-2 whitespace-pre-wrap text-xs opacity-80">{testResult.result}</pre>
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

const TYPE_LABELS: Record<string, string> = {
  python_function: 'Python',
  http_api: 'HTTP',
  sql_query: 'SQL',
  file_operation: '文件',
  search: '搜索',
  web_search: '网络',
}

