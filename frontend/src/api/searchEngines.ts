import { adminApi } from './adminClient'

export interface SearchEngineItem {
  id: string
  tenant_id: string
  name: string
  engine_type: string
  api_base: string | null
  has_api_key: boolean
  extra_params: Record<string, unknown> | null
  is_default: boolean
  is_active: boolean
  priority: number
  created_at: string | null
  updated_at: string | null
}

export interface SearchEngineTypeOption {
  value: string
  label: string
  default_base: string
}

export interface SearchEngineCreatePayload {
  name: string
  engine_type: string
  api_base?: string | null
  api_key?: string | null
  extra_params?: Record<string, unknown> | null
  is_default?: boolean
  is_active?: boolean
  priority?: number
}

export interface SearchEngineUpdatePayload {
  name?: string
  engine_type?: string
  api_base?: string | null
  api_key?: string | null
  extra_params?: Record<string, unknown> | null
  is_default?: boolean
  is_active?: boolean
  priority?: number
}

export interface SearchEngineTestResult {
  success: boolean
  message: string
  result_count: number | null
  first_snippet: string | null
}

export interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

export function listSearchEngines() {
  return adminApi.get<ApiResponse<SearchEngineItem[]>>('/search-engines')
}

export function listEngineTypes() {
  return adminApi.get<ApiResponse<SearchEngineTypeOption[]>>('/search-engines/types')
}

export function createSearchEngine(payload: SearchEngineCreatePayload) {
  return adminApi.post<ApiResponse<SearchEngineItem>>('/search-engines', payload)
}

export function updateSearchEngine(id: string, payload: SearchEngineUpdatePayload) {
  return adminApi.put<ApiResponse<SearchEngineItem>>(`/search-engines/${id}`, payload)
}

export function deleteSearchEngine(id: string) {
  return adminApi.delete<ApiResponse<{ id: string; deleted: boolean }>>(`/search-engines/${id}`)
}

export function toggleSearchEngine(id: string) {
  return adminApi.patch<ApiResponse<SearchEngineItem>>(`/search-engines/${id}/toggle`)
}

export function setDefaultEngine(id: string) {
  return adminApi.put<ApiResponse<SearchEngineItem>>(`/search-engines/${id}/set-default`)
}

export function testSearchEngine(id: string) {
  return adminApi.post<ApiResponse<SearchEngineTestResult>>(`/search-engines/${id}/test`)
}
