import { api } from './client'
import type { ApiResponse, PaginatedData } from './types'

// ==================== 类型定义 ====================

export interface Conversation {
  id: string
  title: string
  is_archived: boolean
  message_count: number
  created_at: string
  updated_at: string
}

export interface ConversationMessage {
  role: string
  content: string
  timestamp: string
}

export interface ConversationDetail extends Conversation {
  messages: ConversationMessage[]
}

export interface ConversationUpdatePayload {
  is_archived?: boolean
  title?: string
}

export interface ConversationListParams {
  archived?: boolean
  page?: number
  page_size?: number
}

// ==================== API 函数 ====================

/** 获取对话列表（支持按归档状态分桶） */
export function listConversations(params?: ConversationListParams) {
  return api.get<ApiResponse<PaginatedData<Conversation>>>('/conversations', { params })
}

/** 获取对话详情（含消息记录） */
export function getConversation(id: string) {
  return api.get<ApiResponse<ConversationDetail>>(`/conversations/${id}`)
}

/** 更新对话（归档 / 取消归档 / 重命名） */
export function updateConversation(id: string, payload: ConversationUpdatePayload) {
  return api.put<ApiResponse<Conversation>>(`/conversations/${id}`, payload)
}

/** 删除对话 */
export function deleteConversation(id: string) {
  return api.delete<ApiResponse<null>>(`/conversations/${id}`)
}

/** 导出对话为指定格式（默认 markdown） */
export function exportConversation(id: string, format: string = 'markdown') {
  return api.post<ApiResponse<string>>(`/conversations/${id}/export`, null, {
    params: { format },
  })
}
