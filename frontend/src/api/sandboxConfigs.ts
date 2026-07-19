import { adminApi } from './adminClient'

export interface SandboxConfigItem {
  id: string
  config_type: string
  name: string
  description: string | null
  config: Record<string, unknown>
  is_active: boolean
  is_system: boolean
  priority: number
}

export interface SandboxConfigCreatePayload {
  config_type: string
  name: string
  description?: string
  config: Record<string, unknown>
  is_active?: boolean
  priority?: number
}

export interface SandboxConfigUpdatePayload {
  name?: string
  description?: string
  config?: Record<string, unknown>
  is_active?: boolean
  priority?: number
}

export interface ConfigTypeItem {
  value: string
  label: string
  description: string
  default_config: Record<string, unknown>
}

export interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

export function listSandboxConfigs(params?: { config_type?: string }) {
  return adminApi.get<ApiResponse<SandboxConfigItem[]>>('/sandbox-configs', { params })
}

export function listConfigTypes() {
  return adminApi.get<ApiResponse<ConfigTypeItem[]>>('/sandbox-configs/types')
}

export function createSandboxConfig(payload: SandboxConfigCreatePayload) {
  return adminApi.post<ApiResponse<SandboxConfigItem>>('/sandbox-configs', payload)
}

export function updateSandboxConfig(id: string, payload: SandboxConfigUpdatePayload) {
  return adminApi.put<ApiResponse<SandboxConfigItem>>(`/sandbox-configs/${id}`, payload)
}

export function deleteSandboxConfig(id: string) {
  return adminApi.delete<ApiResponse<null>>(`/sandbox-configs/${id}`)
}

export function toggleSandboxConfig(id: string) {
  return adminApi.patch<ApiResponse<SandboxConfigItem>>(`/sandbox-configs/${id}/toggle`)
}

export function getActiveConfig(config_type: string) {
  return adminApi.get<ApiResponse<{
    config_type: string
    config: Record<string, unknown>
    source: string
    name?: string
  }>>(`/sandbox-configs/active/${config_type}`)
}

// ============ Phase 7：沙箱实例生命周期 + 执行历史 + 健康检查 ============

export interface SandboxInstanceInfo {
  config_id: string
  config_name: string
  status: 'running' | 'stopped' | 'error'
  started_at: string | null
  stopped_at: string | null
}

export interface SandboxHealthInfo {
  healthy: boolean
  mode?: string
  docker_image?: string
  docker_available?: boolean
  latency_ms?: number
  checked_at: string
  error?: string
}

export interface SandboxTestExecuteParams {
  code: string
  language?: string
  timeout?: number
}

export interface SandboxTestExecuteResult {
  execution_id: string
  success: boolean
  exit_code: number
  stdout: string
  stderr: string
  duration_ms: number
  truncated: boolean
  error_message: string | null
}

export interface SandboxExecutionItem {
  id: string
  config_id: string | null
  trigger_source: string
  language: string
  code: string
  stdout: string | null
  stderr: string | null
  exit_code: number
  duration_ms: number
  truncated: boolean
  success: boolean
  error_message: string | null
  executed_by: string | null
  created_at: string | null
}

export function getSandboxHealth() {
  return adminApi.get<ApiResponse<SandboxHealthInfo>>('/sandbox-configs/health')
}

export function listSandboxInstances() {
  return adminApi.get<ApiResponse<SandboxInstanceInfo[]>>('/sandbox-configs/instances')
}

export function startSandboxInstance(configId: string) {
  return adminApi.post<ApiResponse<SandboxInstanceInfo>>(
    `/sandbox-configs/${configId}/start`,
  )
}

export function stopSandboxInstance(configId: string) {
  return adminApi.post<ApiResponse<SandboxInstanceInfo>>(
    `/sandbox-configs/${configId}/stop`,
  )
}

export function restartSandboxInstance(configId: string) {
  return adminApi.post<ApiResponse<SandboxInstanceInfo>>(
    `/sandbox-configs/${configId}/restart`,
  )
}

export function testExecuteSandbox(
  configId: string,
  params: SandboxTestExecuteParams,
) {
  return adminApi.post<ApiResponse<SandboxTestExecuteResult>>(
    `/sandbox-configs/${configId}/test-execute`,
    {
      code: params.code,
      language: params.language || 'python',
      timeout: params.timeout,
    },
  )
}

export function listSandboxExecutions(
  configId: string,
  params?: { page?: number; page_size?: number },
) {
  return adminApi.get<ApiResponse<{
    total: number
    page: number
    page_size: number
    items: SandboxExecutionItem[]
  }>>(`/sandbox-configs/${configId}/executions`, {
    params: params || {},
  })
}

export function getSandboxExecutionDetail(
  configId: string,
  executionId: string,
) {
  return adminApi.get<ApiResponse<SandboxExecutionItem>>(
    `/sandbox-configs/${configId}/executions/${executionId}`,
  )
}
