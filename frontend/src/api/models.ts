import { adminApi } from './adminClient'

export interface ModelConfigItem {
  id: string
  tenant_id: string
  provider: string
  model_name: string
  display_name: string
  api_base: string
  has_api_key: boolean
  is_default: boolean
  is_active: boolean
  parameters: Record<string, unknown> | null
  created_at: string | null
  updated_at: string | null
}

export interface ModelConfigListParams {
  page?: number
  page_size?: number
  search?: string
  provider?: string
  is_active?: string
}

export interface ModelConfigCreatePayload {
  provider: string
  model_name: string
  display_name: string
  api_base: string
  api_key?: string | null
  is_default?: boolean
  is_active?: boolean
  parameters?: {
    temperature?: number
    max_tokens?: number
    top_p?: number
  } | null
}

export type ModelConfigUpdatePayload = Partial<ModelConfigCreatePayload>

export interface ModelConfigListResponse {
  code: number
  message: string
  data: {
    total: number
    page: number
    page_size: number
    items: ModelConfigItem[]
  }
}

export interface ModelConfigSingleResponse {
  code: number
  message: string
  data: ModelConfigItem
}

export interface ModelTestResponse {
  code: number
  message: string
  data: {
    success: boolean
    message: string
    result: string | null
  }
}

export function listModelConfigs(params: ModelConfigListParams = {}) {
  return adminApi.get<ModelConfigListResponse>('/model-configs', {
    params: {
      page: params.page ?? 1,
      page_size: params.page_size ?? 20,
      search: params.search || '',
      provider: params.provider || '',
      is_active: params.is_active || '',
    },
  })
}

export function createModelConfig(data: ModelConfigCreatePayload) {
  return adminApi.post<ModelConfigSingleResponse>('/model-configs', data)
}

export function updateModelConfig(id: string, data: ModelConfigUpdatePayload) {
  return adminApi.put<ModelConfigSingleResponse>(`/model-configs/${id}`, data)
}

export function deleteModelConfig(id: string) {
  return adminApi.delete<{ code: number; message: string; data: { id: string; deleted: boolean } }>(
    `/model-configs/${id}`,
  )
}

export function toggleModelConfig(id: string) {
  return adminApi.patch<ModelConfigSingleResponse>(`/model-configs/${id}/toggle`)
}

export function testModelConfig(id: string) {
  return adminApi.post<ModelTestResponse>(`/model-configs/${id}/test`)
}

export function setDefaultModelConfig(id: string) {
  return adminApi.post<ModelConfigSingleResponse>(`/model-configs/${id}/set-default`)
}
