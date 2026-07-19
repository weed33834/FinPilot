import { api } from './client'

/**
 * 工具监控 API 客户端
 * 对应后端 /api/v1/tools/（health / circuit-breakers / audit / usage-stats）
 */

export interface ToolHealthStat {
  tool_name?: string
  status?: string
  healthy?: boolean
  total_calls?: number
  success_count?: number
  failure_count?: number
  success_rate?: number
  avg_latency_ms?: number
  last_check_time?: string | null
  last_error?: string | null
  [k: string]: unknown
}

export interface CircuitBreakerState {
  tool_name?: string
  state?: string // CLOSED / OPEN / HALF_OPEN
  failure_count?: number
  success_count?: number
  last_failure_time?: string | null
  last_failure_error?: string | null
  opened_at?: string | null
  [k: string]: unknown
}

export interface ToolAuditRecord {
  id?: string
  tool_name?: string
  params?: unknown
  result?: unknown
  success?: boolean
  latency_ms?: number
  token_count?: number
  error?: string | null
  created_at?: string | null
  timestamp?: string | null
  [k: string]: unknown
}

interface Envelope<T> {
  code: number
  message: string
  data: T
}

/** 获取所有工具健康统计 */
export function getToolHealth() {
  return api.get<Envelope<Record<string, ToolHealthStat>>>('/tools/health')
}

/** 获取单个工具健康统计 */
export function getToolHealthByName(toolName: string) {
  return api.get<Envelope<ToolHealthStat>>(`/tools/${encodeURIComponent(toolName)}/health`)
}

/** 触发主动健康检查 */
export function triggerHealthCheck(toolName: string) {
  return api.post<Envelope<unknown>>(`/tools/${encodeURIComponent(toolName)}/health-check`)
}

/** 获取所有断路器状态 */
export function getCircuitBreakers() {
  return api.get<Envelope<Record<string, CircuitBreakerState>>>('/tools/circuit-breakers')
}

/** 重置断路器 */
export function resetCircuitBreaker(toolName: string) {
  return api.post<Envelope<{ tool_name: string; reset: boolean }>>(
    `/tools/${encodeURIComponent(toolName)}/circuit-breaker/reset`,
  )
}

export interface AuditQueryParams {
  tool_name?: string
  start_time?: string
  end_time?: string
  limit?: number
}

/** 查询工具执行审计轨迹 */
export function getAuditTrail(params: AuditQueryParams = {}) {
  return api.get<Envelope<ToolAuditRecord[]>>('/tools/audit', {
    params: {
      tool_name: params.tool_name || '',
      start_time: params.start_time || '',
      end_time: params.end_time || '',
      limit: params.limit ?? 200,
    },
  })
}

/** 获取工具使用统计 */
export function getUsageStats() {
  return api.get<Envelope<Record<string, unknown>>>('/tools/usage-stats')
}
