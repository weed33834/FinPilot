import { adminApi } from './adminClient'

export interface AgentConfigItem {
  id: string
  tenant_id: string
  name: string
  description: string | null
  agent_type: string
  model_id: string | null
  prompt_id: string | null
  system_prompt: string | null
  max_iterations: number
  temperature: number
  is_active: boolean
  tool_ids: string[]
  skill_ids: string[]
  created_at: string | null
  updated_at: string | null
}

export interface AgentTypeOption {
  value: string
  label: string
  description: string
}

export interface AgentConfigCreatePayload {
  name: string
  description?: string
  agent_type?: string
  model_id?: string
  prompt_id?: string
  system_prompt?: string
  max_iterations?: number
  temperature?: number
  is_active?: boolean
  tool_ids?: string[]
  skill_ids?: string[]
}

export interface AgentConfigUpdatePayload {
  name?: string
  description?: string
  agent_type?: string
  model_id?: string
  prompt_id?: string
  system_prompt?: string
  max_iterations?: number
  temperature?: number
  is_active?: boolean
  tool_ids?: string[]
  skill_ids?: string[]
}

export interface AgentTestPayload {
  message: string
}

export interface AgentTestResult {
  success: boolean
  message: string
  thinking: string | null
  answer: string | null
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

export function listAgentConfigs(params: {
  page?: number
  page_size?: number
  search?: string
  agent_type?: string
  is_active?: string
}) {
  return adminApi.get<ApiResponse<PaginatedData<AgentConfigItem>>>('/agent-configs', { params })
}

export function listAgentTypes() {
  return adminApi.get<ApiResponse<AgentTypeOption[]>>('/agent-configs/types')
}

export function createAgentConfig(payload: AgentConfigCreatePayload) {
  return adminApi.post<ApiResponse<AgentConfigItem>>('/agent-configs', payload)
}

export function updateAgentConfig(id: string, payload: AgentConfigUpdatePayload) {
  return adminApi.put<ApiResponse<AgentConfigItem>>(`/agent-configs/${id}`, payload)
}

export function deleteAgentConfig(id: string) {
  return adminApi.delete<ApiResponse<{ id: string; deleted: boolean }>>(`/agent-configs/${id}`)
}

export function toggleAgentConfig(id: string) {
  return adminApi.patch<ApiResponse<AgentConfigItem>>(`/agent-configs/${id}/toggle`)
}

export function testAgentConfig(id: string, payload: AgentTestPayload) {
  return adminApi.post<ApiResponse<AgentTestResult>>(`/agent-configs/${id}/test`, payload)
}

export function duplicateAgentConfig(id: string) {
  return adminApi.post<ApiResponse<AgentConfigItem>>(`/agent-configs/${id}/duplicate`)
}
