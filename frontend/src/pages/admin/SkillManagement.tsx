import { useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import i18n from '../../i18n/config.ts'
import zhCnResource from '../../i18n/locales/zh-CN/admin-skill.json'
import enResource from '../../i18n/locales/en/admin-skill.json'
import EmptyState from '../../components/ui/EmptyState.tsx'
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

// adminSkill 命名空间按需注册（config.ts 不在本页改动范围内）
const NS = 'adminSkill'
if (!i18n.hasResourceBundle('zh-CN', NS)) {
  i18n.addResourceBundle('zh-CN', NS, zhCnResource)
}
if (!i18n.hasResourceBundle('en', NS)) {
  i18n.addResourceBundle('en', NS, enResource)
}

// --------------- Form Schema ---------------

const makeSkillFormSchema = (t: TFunction) =>
  z.object({
    name: z.string().min(1, t('form.validation.nameRequired')),
    display_name: z.string().min(1, t('form.validation.displayNameRequired')),
    description: z.string().optional(),
    category: z.string().optional(),
    prompt_id: z.string().nullable().optional(),
    system_prompt_override: z.string().nullable().optional(),
    icon: z.string().nullable().optional(),
    tool_ids: z.array(z.string()).optional(),
  })

type FormValues = z.infer<ReturnType<typeof makeSkillFormSchema>>

export default function SkillManagement() {
  const { t } = useTranslation(NS)
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

  const skillFormSchema = useMemo(() => makeSkillFormSchema(t), [t])

  const form = useForm<FormValues>({
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    resolver: zodResolver(skillFormSchema) as any,
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

  const { data: skillsData, isLoading, isError, error, refetch } = useQuery({
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
    onError: (err: unknown) => alert(`${t('errors.createFailed')}: ${getErrorMessage(err)}`),
  })

  const updateMut = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: SkillUpdatePayload }) =>
      updateSkill(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-skills'] })
      setFormOpen(false)
      setEditingId(null)
    },
    onError: (err: unknown) => alert(`${t('errors.updateFailed')}: ${getErrorMessage(err)}`),
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteSkill(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-skills'] })
      setDeleteConfirmId(null)
    },
    onError: (err: unknown) => alert(`${t('errors.deleteFailed')}: ${getErrorMessage(err)}`),
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

  const toolTypeLabel = (type: string) =>
    t(`toolTypes.${type}`, { defaultValue: type })

  const selectedToolIds: string[] = (form.watch('tool_ids') as string[]) || []
  const allTools: ToolItem[] = toolsData?.data?.data?.items ?? []
  const availableTools = allTools.filter((tool) => !selectedToolIds.includes(tool.id))
  const selectedTools = allTools.filter((tool) => selectedToolIds.includes(tool.id))
  const allPrompts: PromptTemplateItem[] = promptsData?.data?.data?.items ?? []

  const items: SkillItem[] = skillsData?.data?.data?.items ?? []
  const total = skillsData?.data?.data?.total ?? 0
  const pageSize = skillsData?.data?.data?.page_size ?? 15
  const totalPages = Math.ceil(total / pageSize)

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-white">{t('title')}</h2>
          <p className="text-sm text-slate-400 mt-1">{t('subtitle')}</p>
        </div>
        <button
          onClick={handleCreate}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 transition-colors"
        >
          + {t('actions.create')}
        </button>
      </div>

      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-3">
        <input
          type="text"
          placeholder={t('search.placeholder')}
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1) }}
          className="w-56 rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white placeholder-slate-400 focus:border-blue-500 focus:outline-none"
        />
        <select
          value={categoryFilter}
          onChange={(e) => { setCategoryFilter(e.target.value); setPage(1) }}
          className="rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
        >
          <option value="">{t('filters.allCategories')}</option>
          {categoriesData?.data?.data?.map((c: string) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        <select
          value={statusFilter}
          onChange={(e) => { setStatusFilter(e.target.value); setPage(1) }}
          className="rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
        >
          <option value="">{t('filters.allStatus')}</option>
          <option value="active">{t('filters.status.active')}</option>
          <option value="inactive">{t('filters.status.inactive')}</option>
        </select>
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="flex items-center justify-center py-20 text-slate-400">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-blue-500 border-t-transparent mr-2" />
          {t('status.loading')}
        </div>
      ) : isError ? (
        <EmptyState
          title={t('errors.loadFailed')}
          description={getErrorMessage(error)}
          icon="empty"
          action={
            <button
              onClick={() => refetch()}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 transition-colors"
            >
              {t('actions.retry')}
            </button>
          }
        />
      ) : items.length === 0 ? (
        <EmptyState title={t('empty.title')} icon="empty" />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-slate-700/50">
          <table className="w-full text-sm">
            <thead className="bg-slate-800/60 text-left text-slate-300">
              <tr>
                <th className="px-4 py-3 font-medium">{t('table.displayName')}</th>
                <th className="px-4 py-3 font-medium">{t('table.category')}</th>
                <th className="px-4 py-3 font-medium">{t('table.tools')}</th>
                <th className="px-4 py-3 font-medium">{t('table.prompt')}</th>
                <th className="px-4 py-3 font-medium">{t('table.status')}</th>
                <th className="px-4 py-3 font-medium">{t('table.actions')}</th>
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
                    {t('table.toolCount', { count: skill.tool_ids?.length || 0 })}
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
                        title={t('actions.test')}
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12" /></svg>
                      </button>
                      <button
                        onClick={() => handleEdit(skill)}
                        className="rounded p-1.5 text-slate-400 hover:bg-slate-700 hover:text-amber-400 transition-colors"
                        title={t('actions.edit')}
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" /><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" /></svg>
                      </button>
                      <button
                        onClick={() => setDeleteConfirmId(skill.id)}
                        className="rounded p-1.5 text-slate-400 hover:bg-slate-700 hover:text-red-400 transition-colors"
                        title={t('actions.delete')}
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
          <span>{t('pagination.total', { total })}</span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
              className="rounded px-3 py-1 border border-slate-700 hover:bg-slate-800 disabled:opacity-40"
            >
              {t('pagination.prev')}
            </button>
            <span>{t('pagination.info', { page, totalPages })}</span>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
              className="rounded px-3 py-1 border border-slate-700 hover:bg-slate-800 disabled:opacity-40"
            >
              {t('pagination.next')}
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
                {editingId ? t('form.editTitle') : t('form.createTitle')}
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
                  <label className="block text-sm font-medium text-slate-300 mb-1">{t('form.name')}</label>
                  <input
                    {...form.register('name')}
                    className="w-full rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1">{t('form.displayName')}</label>
                  <input
                    {...form.register('display_name')}
                    className="w-full rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
                  />
                </div>
              </div>
              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1">{t('form.category')}</label>
                  <select
                    {...form.register('category')}
                    className="w-full rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
                  >
                    <option value="">{t('form.noCategory')}</option>
                    {categoriesData?.data?.data?.map((c: string) => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1">{t('form.promptTemplate')}</label>
                  <select
                    {...form.register('prompt_id')}
                    className="w-full rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
                  >
                    <option value="">{t('form.none')}</option>
                    {allPrompts.map((p: PromptTemplateItem) => (
                      <option key={p.id} value={p.id}>{p.name}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1">{t('form.icon')}</label>
                  <input
                    {...form.register('icon')}
                    className="w-full rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
                  />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">{t('form.description')}</label>
                <textarea
                  {...form.register('description')}
                  rows={3}
                  className="w-full rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">{t('form.systemPromptOverride')}</label>
                <textarea
                  {...form.register('system_prompt_override')}
                  rows={4}
                  className="w-full rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm font-mono text-white focus:border-blue-500 focus:outline-none"
                />
              </div>

              {/* Tool Transfer (Shuttle) */}
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">{t('form.tools')}</label>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <div className="text-xs text-slate-400 mb-1">{t('form.availableTools')}</div>
                    <div className="h-40 overflow-y-auto rounded-lg border border-slate-700 bg-slate-800/50 p-2 space-y-1">
                      {availableTools.map((tool) => (
                        <div
                          key={tool.id}
                          className="flex items-center justify-between rounded px-2 py-1 hover:bg-slate-700/50 cursor-pointer text-sm text-slate-300"
                          onClick={() => {
                            form.setValue('tool_ids', [...selectedToolIds, tool.id])
                          }}
                        >
                          <span>{tool.display_name}</span>
                          <span className="text-xs text-slate-500">{toolTypeLabel(tool.type)}</span>
                        </div>
                      ))}
                      {availableTools.length === 0 && (
                        <div className="text-xs text-slate-500 p-2">{t('form.noAvailableTools')}</div>
                      )}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-400 mb-1">{t('form.selectedTools')}</div>
                    <div className="h-40 overflow-y-auto rounded-lg border border-blue-700/50 bg-blue-900/10 p-2 space-y-1">
                      {selectedTools.map((tool) => (
                        <div
                          key={tool.id}
                          className="flex items-center justify-between rounded px-2 py-1 hover:bg-red-900/20 cursor-pointer text-sm text-blue-300"
                          onClick={() => {
                            form.setValue('tool_ids', selectedToolIds.filter((id) => id !== tool.id))
                          }}
                        >
                          <span>{tool.display_name}</span>
                          <span className="text-xs opacity-60">{t('form.remove')}</span>
                        </div>
                      ))}
                      {selectedTools.length === 0 && (
                        <div className="text-xs text-slate-500 p-2">{t('form.clickToAdd')}</div>
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
                  {t('actions.cancel')}
                </button>
                <button
                  type="submit"
                  disabled={createMut.isPending || updateMut.isPending}
                  className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 transition-colors"
                >
                  {editingId ? t('actions.save') : t('actions.submitCreate')}
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
            <h3 className="text-lg font-semibold text-white mb-2">{t('confirm.deleteTitle')}</h3>
            <p className="text-sm text-slate-400">{t('confirm.deleteMessage')}</p>
            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={() => setDeleteConfirmId(null)}
                className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-300 hover:bg-slate-800"
              >
                {t('actions.cancel')}
              </button>
              <button
                onClick={() => deleteMut.mutate(deleteConfirmId)}
                disabled={deleteMut.isPending}
                className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-500 transition-colors"
              >
                {t('actions.confirmDelete')}
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
                {t('test.title', { name: testTarget.display_name })}
              </h3>
              <button onClick={() => setTestOpen(false)} className="text-slate-400 hover:text-white">
                <ICONS.close size={18} />
              </button>
            </div>
            <div className="space-y-4 px-6 py-4">
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">{t('test.queryLabel')}</label>
                <input
                  value={testQuery}
                  onChange={(e) => setTestQuery(e.target.value)}
                  placeholder={t('test.queryPlaceholder')}
                  className="w-full rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
                />
              </div>
              <button
                onClick={handleTest}
                disabled={testLoading}
                className="rounded-lg bg-cyan-600 px-4 py-2 text-sm font-medium text-white hover:bg-cyan-500 transition-colors"
              >
                {testLoading ? t('status.testing') : t('actions.runTest')}
              </button>
              {testResult && (
                <div className={`rounded-lg p-4 text-sm ${testResult.success ? 'bg-green-900/30 border border-green-700 text-green-300' : 'bg-red-900/30 border border-red-700 text-red-300'}`}>
                  <div className="font-medium mb-1">{testResult.success ? t('status.success') : t('status.failed')}: {testResult.message}</div>
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
