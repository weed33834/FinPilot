import { useCallback, useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { AxiosResponse } from 'axios'
import { api } from '../api/client.ts'
import { getErrorMessage } from '../utils/errors.ts'
import { toast } from '../components/ui/Toaster.tsx'

// 列表响应的常见包裹结构：{ data: { items: [...] } }
interface PaginatedShape<T> {
  data?: { items?: T[] }
}

// 单条记录响应的常见包裹结构：{ data: T }
interface DataShape<T> {
  data?: T
}

export interface CrudOptions<T> {
  /** 资源基础 URL，如 '/users' */
  baseUrl: string
  /** 列表分页大小，默认 50 */
  pageSize?: number
  /** 是否启用编辑（PUT）。ApiKeysPage 无 update 应设 false */
  enableUpdate?: boolean
  /** 创建响应是否包裹在 DataResponse 中。IMUserMappingsPage 返回裸对象应设 false */
  wrapCreateResponse?: boolean
  /** 从列表响应提取 items，默认 response.data.data?.items */
  extractItems?: (response: AxiosResponse) => T[]
  /** 从创建响应提取记录，默认 wrapCreateResponse ? response.data.data : response.data */
  extractCreated?: (response: AxiosResponse) => T | null
  /** 从更新响应提取记录，默认 response.data.data */
  extractUpdated?: (response: AxiosResponse) => T | null
  /** 从记录提取 id，默认 (item) => item.id */
  getId?: (item: T) => string
  /** 错误处理钩子，可在此 toast/alert */
  onError?: (action: string, error: unknown) => void
  /** 成功处理钩子，可在页面自定义 toast */
  onSuccess?: (action: string, item?: T | null) => void
  /** 各动作的错误兜底文案 */
  fetchErrorMessage?: string
  createErrorMessage?: string
  updateErrorMessage?: string
  deleteErrorMessage?: string
  /** 各动作的成功提示文案（传入空字符串则不弹 toast） */
  createSuccessMessage?: string
  updateSuccessMessage?: string
  deleteSuccessMessage?: string
}

export interface CrudResult<T, CreatePayload = unknown, UpdatePayload = CreatePayload> {
  /** 列表数据 */
  items: T[]
  /** 加载中（初始 fetch 与 refresh 期间为 true） */
  loading: boolean
  /** 错误信息（空字符串表示无错误） */
  error: string
  /** 当前操作的记录 id（删除/编辑/特有动作）；创建时为 'creating' */
  actingId: string | null
  /** 重新拉取列表 */
  refresh: () => Promise<void>
  /** 创建记录，失败返回 null */
  create: (payload: CreatePayload) => Promise<T | null>
  /** 更新记录（enableUpdate=false 时抛错），失败返回 null */
  update: (id: string, payload: UpdatePayload) => Promise<T | null>
  /** 删除记录，失败返回 false */
  remove: (id: string) => Promise<boolean>
  /** 设置 actingId（页面特有动作前调用） */
  setActingId: (id: string | null) => void
  /** 设置错误信息（页面特有校验失败时调用） */
  setError: (msg: string) => void
  /** 清空错误 */
  clearError: () => void
}

export function useCrudResource<
  T extends { id?: string },
  CreatePayload = unknown,
  UpdatePayload = CreatePayload,
>(
  options: CrudOptions<T>,
): CrudResult<T, CreatePayload, UpdatePayload> {
  const {
    baseUrl,
    pageSize = 50,
    enableUpdate = true,
    wrapCreateResponse = true,
    onError,
    onSuccess,
    createErrorMessage = '创建失败',
    updateErrorMessage = '更新失败',
    deleteErrorMessage = '删除失败',
    createSuccessMessage = '创建成功',
    updateSuccessMessage = '更新成功',
    deleteSuccessMessage = '删除成功',
  } = options as CrudOptions<T>

  // 默认提取函数
  const extractItemsFn = useMemo(
    () =>
      options.extractItems ??
      ((resp: AxiosResponse) => {
        const data = resp.data as PaginatedShape<T>
        return data?.data?.items ?? []
      }),
    [options.extractItems],
  )

  const extractCreatedFn = useMemo(
    () =>
      options.extractCreated ??
      ((resp: AxiosResponse) => {
        if (wrapCreateResponse) {
          const data = resp.data as DataShape<T>
          return data.data ?? null
        }
        return resp.data as T
      }),
    [options.extractCreated, wrapCreateResponse],
  )

  const extractUpdatedFn = useMemo(
    () =>
      options.extractUpdated ??
      ((resp: AxiosResponse) => {
        const data = resp.data as DataShape<T>
        return data.data ?? null
      }),
    [options.extractUpdated],
  )

  const queryClient = useQueryClient()

  const [actingId, setActingId] = useState<string | null>(null)
  const [error, setError] = useState('')

  // --- useQuery：自动获取列表 ---
  const { data: items = [], isLoading: loading, refetch } = useQuery<T[]>({
    queryKey: [baseUrl, pageSize],
    queryFn: async () => {
      const resp = await api.get(baseUrl, { params: { page: 1, page_size: pageSize } })
      return extractItemsFn(resp)
    },
    staleTime: 30_000,
  })

  const refresh = useCallback(async () => {
    await refetch()
  }, [refetch])

  // --- useMutation：创建 ---
  const createMutation = useMutation<T | null, unknown, CreatePayload>({
    mutationFn: async (payload) => {
      const resp = await api.post(baseUrl, payload)
      return extractCreatedFn(resp)
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: [baseUrl] })
      if (createSuccessMessage) toast.success(createSuccessMessage)
      onSuccess?.('create', data)
    },
    onError: (err) => {
      const msg = getErrorMessage(err, createErrorMessage)
      setError(msg)
      toast.error(msg)
      onError?.('create', err)
    },
    onSettled: () => setActingId(null),
  })

  const create = useCallback(
    async (payload: CreatePayload): Promise<T | null> => {
      setActingId('creating')
      setError('')
      return createMutation.mutateAsync(payload)
    },
    [createMutation],
  )

  // --- useMutation：更新 ---
  const updateMutation = useMutation<T | null, unknown, { id: string; payload: UpdatePayload }>({
    mutationFn: async ({ id, payload }) => {
      const resp = await api.put(`${baseUrl}/${id}`, payload)
      return extractUpdatedFn(resp)
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: [baseUrl] })
      if (updateSuccessMessage) toast.success(updateSuccessMessage)
      onSuccess?.('update', data)
    },
    onError: (err) => {
      const msg = getErrorMessage(err, updateErrorMessage)
      setError(msg)
      toast.error(msg)
      onError?.('update', err)
    },
    onSettled: () => setActingId(null),
  })

  const update = useCallback(
    async (id: string, payload: UpdatePayload): Promise<T | null> => {
      if (!enableUpdate) {
        throw new Error('update not enabled for this resource')
      }
      setActingId(id)
      setError('')
      return updateMutation.mutateAsync({ id, payload })
    },
    [enableUpdate, updateMutation],
  )

  // --- useMutation：删除 ---
  const removeMutation = useMutation<boolean, unknown, string>({
    mutationFn: async (id) => {
      await api.delete(`${baseUrl}/${id}`)
      return true
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [baseUrl] })
      if (deleteSuccessMessage) toast.success(deleteSuccessMessage)
      onSuccess?.('delete')
    },
    onError: (err) => {
      const msg = getErrorMessage(err, deleteErrorMessage)
      setError(msg)
      toast.error(msg)
      onError?.('delete', err)
    },
    onSettled: () => setActingId(null),
  })

  const remove = useCallback(
    async (id: string): Promise<boolean> => {
      setActingId(id)
      setError('')
      return removeMutation.mutateAsync(id)
    },
    [removeMutation],
  )

  const clearError = useCallback(() => setError(''), [])

  return {
    items,
    loading,
    error,
    actingId,
    refresh,
    create,
    update,
    remove,
    setActingId,
    setError,
    clearError,
  }
}
