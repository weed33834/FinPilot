import { api } from './client'

/**
 * 上下文管理 API 客户端
 * 对应后端 /api/v1/context/ 路由（见 backend/app/routers/context_manager.py）
 */

export interface TokenCountResult {
  token_count: number
  char_count: number
  model?: string
  [k: string]: unknown
}

export interface OptimizeContextResult {
  messages?: unknown[]
  system_prompt?: string
  estimated_tokens?: number
  truncated?: boolean
  [k: string]: unknown
}

export interface MemoryItem {
  id: string
  user_id?: string | null
  category?: string | null
  content?: string | null
  importance?: number | null
  source_conversation_id?: string | null
  created_at?: string | null
  updated_at?: string | null
  [k: string]: unknown
}

export interface ContextStats {
  total_memories?: number
  avg_tokens_per_conversation?: number
  total_conversations?: number
  [k: string]: unknown
}

interface ApiEnvelope<T> {
  code?: number
  message?: string
  data: T
}

/** 计算文本 token 数 */
export async function countTokens(text: string, model?: string): Promise<ApiEnvelope<TokenCountResult>> {
  const res = await api.post('/context/count-tokens', { text, model })
  return res.data
}

/** 优化上下文（压缩 / 裁剪消息历史） */
export async function optimizeContext(
  messages: unknown[],
  systemPrompt: string,
  model?: string,
): Promise<ApiEnvelope<OptimizeContextResult>> {
  const res = await api.post('/context/optimize', { messages, system_prompt: systemPrompt, model })
  return res.data
}

/** 获取长期记忆列表 */
export async function getMemories(userId?: string, category?: string): Promise<ApiEnvelope<MemoryItem[]>> {
  const params = new URLSearchParams()
  if (userId) params.set('user_id', userId)
  if (category) params.set('category', category)
  const res = await api.get(`/context/memories?${params.toString()}`)
  return res.data
}

/** 语义搜索长期记忆 */
export async function searchMemories(query: string): Promise<ApiEnvelope<MemoryItem[]>> {
  const res = await api.post('/context/memories/search', { query })
  return res.data
}

/** 删除一条长期记忆 */
export async function deleteMemory(id: string): Promise<ApiEnvelope<{ deleted: boolean }>> {
  const res = await api.delete(`/context/memories/${id}`)
  return res.data
}

/** 获取上下文使用统计 */
export async function getContextStats(): Promise<ApiEnvelope<ContextStats>> {
  const res = await api.get('/context/stats')
  return res.data
}
