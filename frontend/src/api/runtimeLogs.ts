import { adminApi } from './adminClient'

/** 统一响应包装 */
export interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

/** 运行日志条目 */
export interface RuntimeLogItem {
  id: string
  tenant_id: string | null
  category: string
  level: string
  source: string
  event: string
  message: string | null
  payload_json: string | null
  duration_ms: number | null
  status_code: number | null
  user_id: string | null
  ip_address: string | null
  session_id: string | null
  success: boolean
  created_at: string | null
}

/** 统计聚合 */
export interface RuntimeLogStats {
  total: number
  today: number
  by_category: Record<string, number>
  by_level: Record<string, number>
  by_source: Record<string, number>
  success_rate: number
  recent_errors: RuntimeLogItem[]
}

/** 模块状态条目 */
export interface RuntimeLogModuleItem {
  key: string
  label: string
  total: number
  active: number
  inactive: number
}

/** 模块状态响应 */
export interface RuntimeLogModuleStatus {
  modules: RuntimeLogModuleItem[]
  checked_at: string
}

/** 最近会话消息 */
export interface RuntimeLogMessageItem {
  id: string
  conversation_id: string
  role: string
  content: string | null
  created_at: string | null
}

/** 会话汇总 */
export interface RuntimeLogConversations {
  total_conversations: number
  total_messages: number
  user_messages: number
  assistant_messages: number
  recent: RuntimeLogMessageItem[]
}

/** 列表查询参数 */
export interface RuntimeLogListParams {
  category?: string
  source?: string
  level?: string
  success?: boolean | string
  session_id?: string
  keyword?: string
  start_time?: string
  end_time?: string
  page?: number
  page_size?: number
}

/** 列表响应 */
export interface RuntimeLogListResult {
  items: RuntimeLogItem[]
  total: number
  page: number
  page_size: number
}

/** 批量清理参数 */
export interface RuntimeLogBatchDeleteParams {
  category?: string
  before_days?: number
}

/** 批量清理响应 */
export interface RuntimeLogBatchDeleteResult {
  deleted_count: number
}

/** 导出响应 */
export interface RuntimeLogExportResult {
  exported_at: string
  count: number
  items: RuntimeLogItem[]
}

/** 获取统计 */
export function getRuntimeStats() {
  return adminApi.get<ApiResponse<RuntimeLogStats>>('/runtime-logs/stats')
}

/** 列表查询 */
export function listRuntimeLogs(params?: RuntimeLogListParams) {
  return adminApi.get<ApiResponse<RuntimeLogListResult>>('/runtime-logs', {
    params: params || {},
  })
}

/** 单条详情 */
export function getRuntimeLogDetail(id: string) {
  return adminApi.get<ApiResponse<RuntimeLogItem>>(`/runtime-logs/${id}`)
}

/** 删除单条 */
export function deleteRuntimeLog(id: string) {
  return adminApi.delete<ApiResponse<null>>(`/runtime-logs/${id}`)
}

/** 批量清理 */
export function batchDeleteRuntimeLogs(params?: RuntimeLogBatchDeleteParams) {
  return adminApi.delete<ApiResponse<RuntimeLogBatchDeleteResult>>('/runtime-logs', {
    params: params || {},
  })
}

/** 导出当前筛选范围 */
export function exportRuntimeLogs(params?: RuntimeLogListParams) {
  return adminApi.get<ApiResponse<RuntimeLogExportResult>>('/runtime-logs/export', {
    params: params || {},
  })
}

/** 模块状态 */
export function getModuleStatus() {
  return adminApi.get<ApiResponse<RuntimeLogModuleStatus>>('/runtime-logs/module-status')
}

/** 问答交互汇总 */
export function getConversationsSummary() {
  return adminApi.get<ApiResponse<RuntimeLogConversations>>('/runtime-logs/conversations')
}

/** 解析 payload_json 字符串 */
export function parsePayloadJson(raw: string | null): unknown {
  if (!raw) return null
  try {
    return JSON.parse(raw)
  } catch {
    return raw
  }
}
