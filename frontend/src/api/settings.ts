import { adminApi } from './adminClient'

export interface SystemSettingsData {
  system_name: string
  system_description: string
  default_model_id: string | null
  default_search_engine_id: string | null
  max_conversation_history: number
  session_timeout_minutes: number
  rate_limit_per_minute: number
  log_level: string
  enable_telemetry: boolean
  sandbox_mode: string
  max_file_upload_mb: number
}

export interface SettingsUpdatePayload {
  system_name?: string
  system_description?: string
  default_model_id?: string | null
  default_search_engine_id?: string | null
  max_conversation_history?: number
  session_timeout_minutes?: number
  rate_limit_per_minute?: number
  log_level?: string
  enable_telemetry?: boolean
  sandbox_mode?: string
  max_file_upload_mb?: number
}

export interface HealthStatus {
  status: string
  database: { status: string; latency_ms: number }
  vector_store: { status: string; message?: string }
  default_llm: { status: string; model_name: string }
  sandbox: { status: string }
  search_engines: { total: number; active: number; default_name: string }
  timestamp: string
}

export interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

export function getSettings() {
  return adminApi.get<ApiResponse<SystemSettingsData>>('/settings')
}

export function updateSettings(payload: SettingsUpdatePayload) {
  return adminApi.put<ApiResponse<SystemSettingsData>>('/settings', payload)
}

export function getHealthCheck() {
  return adminApi.get<ApiResponse<HealthStatus>>('/settings/health')
}
