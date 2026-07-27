import { api } from './client'
import type { ApiResponse, PaginatedData } from './types'
import type { Document } from '../types/document'

// ==================== 类型定义 ====================

export interface DocumentListParams {
  status?: string
  page?: number
  page_size?: number
}

// ==================== API 函数 ====================

/** 获取文档列表（支持按解析状态筛选） */
export function listDocuments(params?: DocumentListParams) {
  return api.get<ApiResponse<PaginatedData<Document>>>('/documents', { params })
}

/** 获取单条文档详情 */
export function getDocument(id: string) {
  return api.get<ApiResponse<Document>>(`/documents/${id}`)
}

/** 上传文档并触发解析 */
export function uploadDocument(file: File) {
  const formData = new FormData()
  formData.append('file', file)
  return api.post<ApiResponse<Document>>('/documents/upload', formData)
}

/** 删除文档 */
export function deleteDocument(id: string) {
  return api.delete<ApiResponse<null>>(`/documents/${id}`)
}
