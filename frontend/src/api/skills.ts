import { adminApi } from './adminClient'

export interface SkillItem {
  id: string
  tenant_id: string
  name: string
  display_name: string
  description: string | null
  category: string
  prompt_id: string | null
  system_prompt_override: string | null
  is_active: boolean
  icon: string | null
  tool_ids: string[]
  created_at: string | null
  updated_at: string | null
}

export interface SkillCreatePayload {
  name: string
  display_name: string
  description?: string
  category: string
  prompt_id?: string | null
  system_prompt_override?: string | null
  icon?: string | null
  tool_ids?: string[]
  is_active?: boolean
}

export interface SkillUpdatePayload {
  display_name?: string
  description?: string
  category?: string
  prompt_id?: string | null
  system_prompt_override?: string | null
  icon?: string | null
  tool_ids?: string[]
}

export interface SkillTestResult {
  success: boolean
  message: string
  result: string | null
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

export function listSkills(params: {
  page?: number
  page_size?: number
  search?: string
  category?: string
  is_active?: string
}) {
  return adminApi.get<ApiResponse<PaginatedData<SkillItem>>>('/skills', { params })
}

export function listSkillCategories() {
  return adminApi.get<ApiResponse<string[]>>('/skills/categories')
}

export function createSkill(payload: SkillCreatePayload) {
  return adminApi.post<ApiResponse<SkillItem>>('/skills', payload)
}

export function updateSkill(id: string, payload: SkillUpdatePayload) {
  return adminApi.put<ApiResponse<SkillItem>>(`/skills/${id}`, payload)
}

export function deleteSkill(id: string) {
  return adminApi.delete<ApiResponse<{ id: string; deleted: boolean }>>(`/skills/${id}`)
}

export function toggleSkill(id: string) {
  return adminApi.patch<ApiResponse<SkillItem>>(`/skills/${id}/toggle`)
}

export function getSkillTools(id: string) {
  return adminApi.get<ApiResponse<string[]>>(`/skills/${id}/tools`)
}

export function updateSkillTools(id: string, tool_ids: string[]) {
  return adminApi.put<ApiResponse<SkillItem>>(`/skills/${id}/tools`, { tool_ids })
}

export function testSkill(id: string, query: string) {
  return adminApi.post<ApiResponse<SkillTestResult>>(`/skills/${id}/test`, { query })
}
