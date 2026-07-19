import { adminApi } from './adminClient'

export interface ToolItem {
  id: string
  tenant_id: string
  name: string
  display_name: string
  description: string | null
  type: string
  is_builtin: boolean
  is_active: boolean
  has_api_key: boolean
  config: Record<string, unknown>
  created_at: string | null
  updated_at: string | null
}

export interface ToolTypeOption {
  value: string
  label: string
  description: string
}

export interface ToolCreatePayload {
  name: string
  display_name: string
  description?: string
  type: string
  config?: Record<string, unknown>
  api_key?: string
}

export interface ToolUpdatePayload {
  display_name?: string
  description?: string
  config?: Record<string, unknown>
  api_key?: string
}

export interface ToolTestPayload {
  parameters: Record<string, unknown>
}

export interface ToolTestResult {
  success: boolean
  message: string
  result: string | null
  execution_time_ms: number
}

export interface PaginatedData<T> {
  total: number
  page: number
  page_size: number
  items: T[]
}

export interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

export function listTools(params: {
  page?: number
  page_size?: number
  search?: string
  type?: string
  is_active?: string
  is_builtin?: string
}) {
  return adminApi.get<ApiResponse<PaginatedData<ToolItem>>>('/tools', { params })
}

export function listToolTypes() {
  return adminApi.get<ApiResponse<ToolTypeOption[]>>('/tools/types')
}

export function createTool(payload: ToolCreatePayload) {
  return adminApi.post<ApiResponse<ToolItem>>('/tools', payload)
}

export function updateTool(id: string, payload: ToolUpdatePayload) {
  return adminApi.put<ApiResponse<ToolItem>>(`/tools/${id}`, payload)
}

export function deleteTool(id: string) {
  return adminApi.delete<ApiResponse<{ id: string; deleted: boolean }>>(`/tools/${id}`)
}

export function toggleTool(id: string) {
  return adminApi.patch<ApiResponse<ToolItem>>(`/tools/${id}/toggle`)
}

export function testTool(id: string, payload: ToolTestPayload) {
  return adminApi.post<ApiResponse<ToolTestResult>>(`/tools/${id}/test`, payload)
}

export function duplicateTool(id: string) {
  return adminApi.post<ApiResponse<ToolItem>>(`/tools/${id}/duplicate`)
}
