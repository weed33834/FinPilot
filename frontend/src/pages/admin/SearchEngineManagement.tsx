import { useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import i18n from '../../i18n/config.ts'
import zhCnResource from '../../i18n/locales/zh-CN/admin-search-engine.json'
import enResource from '../../i18n/locales/en/admin-search-engine.json'
import EmptyState from '../../components/ui/EmptyState.tsx'
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

// 命名空间未在 i18n/config.ts 中注册（按要求不修改该文件），这里在模块加载时
// 同步注入资源，组件通过 useTranslation('adminSearchEngine') 消费。
const NS = 'adminSearchEngine'
if (!i18n.hasResourceBundle('zh-CN', NS)) {
  i18n.addResourceBundle('zh-CN', NS, zhCnResource)
}
if (!i18n.hasResourceBundle('en', NS)) {
  i18n.addResourceBundle('en', NS, enResource)
}

const ENGINE_BADGES: Record<string, string> = {
  google: 'bg-red-900/30 text-red-300 border-red-700',
  bing: 'bg-blue-900/30 text-blue-300 border-blue-700',
  duckduckgo: 'bg-amber-900/30 text-amber-300 border-amber-700',
  serpapi: 'bg-green-900/30 text-green-300 border-green-700',
  tavily: 'bg-purple-900/30 text-purple-300 border-purple-700',
  searxng: 'bg-cyan-900/30 text-cyan-300 border-cyan-700',
}

// 枚举值（value）用于 API 提交保持原值，仅显示 label 走 i18n
const ENGINE_TYPES = [
  { value: 'google', label: 'Google Custom Search' },
  { value: 'bing', label: 'Bing' },
  { value: 'duckduckgo', label: 'DuckDuckGo' },
  { value: 'serpapi', label: 'SerpAPI' },
  { value: 'tavily', label: 'Tavily' },
  { value: 'searxng', label: 'SearXNG' },
]

const SAFE_SEARCH_OPTIONS = [
  { value: '', key: 'default' },
  { value: 'off', key: 'off' },
  { value: 'medium', key: 'medium' },
  { value: 'high', key: 'high' },
]

const makeFormSchema = (t: TFunction) =>
  z.object({
    name: z.string().min(1, t('form.validation.nameRequired')),
    engine_type: z.string().min(1, t('form.validation.engineTypeRequired')),
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

type FormValues = z.infer<ReturnType<typeof makeFormSchema>>

interface ExtraParamRow {
  key: string
  value: string
}

export default function SearchEngineManagement() {
  const { t } = useTranslation('adminSearchEngine')
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

  const formSchema = useMemo(() => makeFormSchema(t), [t])

  const form = useForm<FormValues>({
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
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

  const { data: enginesData, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['admin-search-engines'],
    queryFn: () => listSearchEngines().then((r) => r.data),
  })

  const createMut = useMutation({
    mutationFn: (payload: SearchEngineCreatePayload) => createSearchEngine(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-search-engines'] })
      setFormOpen(false)
    },
    onError: (err: unknown) => alert(t('messages.createFailed', { error: getErrorMessage(err) })),
  })

  const updateMut = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: SearchEngineUpdatePayload }) =>
      updateSearchEngine(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-search-engines'] })
      setFormOpen(false)
      setEditingId(null)
    },
    onError: (err: unknown) => alert(t('messages.updateFailed', { error: getErrorMessage(err) })),
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteSearchEngine(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-search-engines'] })
      setDeleteConfirmId(null)
    },
    onError: (err: unknown) => alert(t('messages.deleteFailed', { error: getErrorMessage(err) })),
  })

  const toggleMut = useMutation({
    mutationFn: (id: string) => toggleSearchEngine(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin-search-engines'] }),
  })

  const setDefaultMut = useMutation({
    mutationFn: (id: string) => setDefaultEngine(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin-search-engines'] }),
    onError: (err: unknown) => alert(t('messages.operationFailed', { error: getErrorMessage(err) })),
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
      setTestResult({ success: false, message: getErrorMessage(err, t('messages.testFailed')), result_count: null, first_snippet: null })
    } finally {
      setTestLoading(false)
    }
  }

  const engineTypeLabel = (value: string) =>
    t(`engineTypes.${value}`, { defaultValue: ENGINE_TYPES.find((o) => o.value === value)?.label || value })

  const allItems: SearchEngineItem[] = enginesData?.data ?? []
  const items = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return allItems
    return allItems.filter(
      (e) =>
        e.name.toLowerCase().includes(q) ||
        e.engine_type.toLowerCase().includes(q),
    )
  }, [allItems, search])

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-white">{t('title')}</h2>
        <button
          onClick={handleCreate}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 transition-colors"
        >
          + {t('actions.add')}
        </button>
      </div>

      {/* Toolbar */}
      <div className="flex items-center gap-3">
        <input
          type="text"
          placeholder={t('search.placeholder')}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-56 rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white placeholder-slate-400 focus:border-blue-500 focus:outline-none"
        />
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
              onClick={() => void refetch()}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 transition-colors"
            >
              <ICONS.refresh size={14} className="inline mr-1" />
              {t('actions.retry')}
            </button>
          }
        />
      ) : items.length === 0 ? (
        <EmptyState title={t('empty.noEngines')} icon="empty" />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-slate-700/50">
          <table className="w-full text-sm">
            <thead className="bg-slate-800/60 text-left text-slate-300">
              <tr>
                <th className="px-4 py-3 font-medium">{t('table.name')}</th>
                <th className="px-4 py-3 font-medium">{t('table.type')}</th>
                <th className="px-4 py-3 font-medium">{t('table.apiBase')}</th>
                <th className="px-4 py-3 font-medium">{t('table.default')}</th>
                <th className="px-4 py-3 font-medium">{t('table.priority')}</th>
                <th className="px-4 py-3 font-medium">{t('table.status')}</th>
                <th className="px-4 py-3 font-medium">{t('table.actions')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700/30">
              {items.map((engine) => (
                <tr key={engine.id} className="hover:bg-slate-800/30 transition-colors">
                  <td className="px-4 py-3 font-medium text-white">{engine.name}</td>
                  <td className="px-4 py-3">
                    <span className={`rounded border px-2 py-0.5 text-xs ${ENGINE_BADGES[engine.engine_type] || 'bg-slate-700 text-slate-300 border-slate-600'}`}>
                      {engineTypeLabel(engine.engine_type)}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-400 max-w-[200px] truncate">
                    {engine.api_base || '-'}
                  </td>
                  <td className="px-4 py-3">
                    {engine.is_default ? (
                      <span className="text-yellow-400" title={t('status.defaultEngine')}>
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                          <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
                        </svg>
                      </span>
                    ) : (
                      <button
                        onClick={() => setDefaultMut.mutate(engine.id)}
                        className="text-slate-600 hover:text-yellow-400 transition-colors"
                        title={t('actions.setAsDefault')}
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
                        title={t('actions.testSearch')}
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12" /></svg>
                      </button>
                      <button
                        onClick={() => handleEdit(engine)}
                        className="rounded p-1.5 text-slate-400 hover:bg-slate-700 hover:text-amber-400 transition-colors"
                        title={t('actions.edit')}
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" /><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" /></svg>
                      </button>
                      <button
                        onClick={() => setDeleteConfirmId(engine.id)}
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

      {/* Create/Edit Dialog */}
      {formOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="w-[600px] max-h-[85vh] overflow-y-auto rounded-xl border border-slate-700 bg-slate-900 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-700 px-6 py-4">
              <h3 className="text-lg font-semibold text-white">
                {editingId ? t('form.editTitle') : t('form.createTitle')}
              </h3>
              <button onClick={() => { setFormOpen(false); setEditingId(null) }} className="text-slate-400 hover:text-white">
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
                  <label className="block text-sm font-medium text-slate-300 mb-1">{t('form.engineType')}</label>
                  <select
                    {...form.register('engine_type')}
                    className="w-full rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
                  >
                    <option value="">{t('form.selectType')}</option>
                    {ENGINE_TYPES.map((opt) => (
                      <option key={opt.value} value={opt.value}>{engineTypeLabel(opt.value)}</option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1">{t('form.apiBase')}</label>
                  <input
                    {...form.register('api_base')}
                    className="w-full rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1">{t('form.apiKey')}</label>
                  <input
                    {...form.register('api_key')}
                    type="password"
                    className="w-full rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
                  />
                </div>
              </div>

              {/* Extra Params */}
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">{t('form.builtinParams')}</label>
                <div className="grid grid-cols-2 gap-3 mb-3">
                  <div>
                    <label className="text-xs text-slate-400">{t('form.cx')}</label>
                    <input
                      {...form.register('extra_params.cx')}
                      className="w-full rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-slate-400">{t('form.region')}</label>
                    <input
                      {...form.register('extra_params.region')}
                      className="w-full rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-slate-400">{t('form.safeSearch')}</label>
                    <select
                      {...form.register('extra_params.safe_search')}
                      className="w-full rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
                    >
                      {SAFE_SEARCH_OPTIONS.map((opt) => (
                        <option key={opt.key} value={opt.value}>{t(`safeSearchOptions.${opt.key}`)}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="text-xs text-slate-400">{t('form.maxResults')}</label>
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
                <label className="block text-sm font-medium text-slate-300 mb-1">{t('form.priority')}</label>
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
                  <label className="text-sm font-medium text-slate-300">{t('form.customParams')}</label>
                  <button
                    type="button"
                    onClick={() => setExtraRows([...extraRows, { key: '', value: '' }])}
                    className="rounded px-2 py-1 text-xs text-blue-400 hover:bg-slate-800"
                  >
                    + {t('actions.addParam')}
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
                      placeholder={t('form.paramKeyPlaceholder')}
                      className="w-1/3 rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-1.5 text-sm text-white focus:border-blue-500 focus:outline-none"
                    />
                    <input
                      value={row.value}
                      onChange={(e) => {
                        const updated = [...extraRows]
                        updated[idx] = { ...row, value: e.target.value }
                        setExtraRows(updated)
                      }}
                      placeholder={t('form.paramValuePlaceholder')}
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
                  {t('actions.cancel')}
                </button>
                <button
                  type="submit"
                  disabled={createMut.isPending || updateMut.isPending}
                  className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 transition-colors"
                >
                  {editingId ? t('actions.save') : t('actions.create')}
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
              <button onClick={() => setDeleteConfirmId(null)} className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-300 hover:bg-slate-800">
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
                {t('test.title', { name: testTarget.name })}
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
                {testLoading ? t('status.testing') : t('test.button')}
              </button>
              {testResult && (
                <div className={`rounded-lg p-4 text-sm ${testResult.success ? 'bg-green-900/30 border border-green-700 text-green-300' : 'bg-red-900/30 border border-red-700 text-red-300'}`}>
                  <div className="font-medium mb-1">{testResult.success ? t('test.success') : t('test.failed')}: {testResult.message}</div>
                  {testResult.success && (
                    <div className="mt-1 text-xs opacity-80">{t('test.resultCount', { count: testResult.result_count })}</div>
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
