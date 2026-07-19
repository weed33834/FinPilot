import { adminApi } from './adminClient'

export interface McpServerItem {
  id: string
  name: string
  display_name: string
  description: string | null
  transport: string
  command: string | null
  args: string | null
  url: string | null
  env_vars: Record<string, string>
  is_active: boolean
  is_builtin: boolean
  priority: number
  last_connected_at: string | null
  last_status: string | null
}

export interface McpServerCreatePayload {
  name: string
  display_name: string
  description?: string
  transport: string
  command?: string | null
  args?: string | null
  url?: string | null
  api_key?: string | null
  env_vars?: Record<string, string>
  is_active?: boolean
  priority?: number
}

export interface McpServerUpdatePayload {
  display_name?: string
  description?: string
  transport?: string
  command?: string | null
  args?: string | null
  url?: string | null
  api_key?: string | null
  env_vars?: Record<string, string>
  is_active?: boolean
  priority?: number
}

export interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

export function listMcpServers(params?: { active_only?: boolean }) {
  return adminApi.get<ApiResponse<McpServerItem[]>>('/mcp-servers', { params })
}

export function listTransports() {
  return adminApi.get<ApiResponse<{ value: string; label: string }[]>>('/mcp-servers/transports')
}

export function createMcpServer(payload: McpServerCreatePayload) {
  return adminApi.post<ApiResponse<McpServerItem>>('/mcp-servers', payload)
}

export function updateMcpServer(id: string, payload: McpServerUpdatePayload) {
  return adminApi.put<ApiResponse<McpServerItem>>(`/mcp-servers/${id}`, payload)
}

export function deleteMcpServer(id: string) {
  return adminApi.delete<ApiResponse<null>>(`/mcp-servers/${id}`)
}

export function toggleMcpServer(id: string) {
  return adminApi.patch<ApiResponse<McpServerItem>>(`/mcp-servers/${id}/toggle`)
}

export function testMcpServer(id: string) {
  return adminApi.post<ApiResponse<{ status: string; name: string; transport: string }>>(`/mcp-servers/${id}/test`)
}

export function listMcpTools(id: string) {
  return adminApi.get<ApiResponse<{ server_name: string; tools: unknown[]; note: string }>>(`/mcp-servers/${id}/tools`)
}
