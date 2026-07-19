import { api } from './client'

export interface PromptTemplateItem {
  id: string
  tenant_id: string
  name: string
  description: string | null
  template_type: string
  content: string
  variables: string[] | null
  is_system: boolean
  is_active: boolean
  created_by: string | null
  created_at: string
  updated_at: string
}

export interface PromptListParams {
  page?: number
  page_size?: number
  search?: string
  template_type?: string
  is_active?: string
}

export interface PromptCreatePayload {
  name: string
  description?: string | null
  template_type?: string
  content: string
  variables?: string[] | null
}

export type PromptUpdatePayload = Partial<PromptCreatePayload>

export interface PromptListResponse {
  code: number
  message: string
  data: {
    total: number
    page: number
    page_size: number
    items: PromptTemplateItem[]
  }
}

export interface PromptSingleResponse {
  code: number
  message: string
  data: PromptTemplateItem
}

export interface PromptRenderPayload {
  template_id?: string | null
  content?: string | null
  variables: Record<string, string>
}

export interface PromptRenderResponse {
  code: number
  message: string
  data: {
    rendered: string
  }
}

export interface PromptCategoriesResponse {
  code: number
  message: string
  data: string[]
}

export function listPrompts(params: PromptListParams = {}) {
  return api.get<PromptListResponse>('/prompts', {
    params: {
      page: params.page ?? 1,
      page_size: params.page_size ?? 20,
      search: params.search || '',
      template_type: params.template_type || '',
      is_active: params.is_active || '',
    },
  })
}

export function getPrompt(id: string) {
  return api.get<PromptSingleResponse>(`/prompts/${id}`)
}

export function createPrompt(data: PromptCreatePayload) {
  return api.post<PromptSingleResponse>('/prompts', data)
}

export function updatePrompt(id: string, data: PromptUpdatePayload) {
  return api.put<PromptSingleResponse>(`/prompts/${id}`, data)
}

export function deletePrompt(id: string) {
  return api.delete<{ code: number; message: string; data: null }>(`/prompts/${id}`)
}

export function togglePrompt(id: string) {
  return api.put<PromptSingleResponse>(`/prompts/${id}/toggle`)
}

export function duplicatePrompt(id: string) {
  return api.post<PromptSingleResponse>(`/prompts/${id}/duplicate`)
}

export function renderPrompt(payload: PromptRenderPayload) {
  return api.post<PromptRenderResponse>('/prompts/render', payload)
}

export function getPromptCategories() {
  return api.get<PromptCategoriesResponse>('/prompts/categories/list')
}

// ---------------------------------------------------------------------------
// AI 自动生成提示词 + 导入 / 导出（外部资源）
// ---------------------------------------------------------------------------

export interface PromptAIGenerateParams {
  description: string
  template_type?: string
  tone?: string
  language?: string
}

export interface PromptAIGenerateResult {
  name: string
  description: string
  template_type: string
  content: string
  variables: string[]
}

export interface PromptAIGenerateResponse {
  code: number
  message: string
  data: PromptAIGenerateResult
}

export function aiGeneratePrompt(params: PromptAIGenerateParams) {
  return api.post<PromptAIGenerateResponse>('/prompts/ai-generate', {
    description: params.description,
    template_type: params.template_type || 'general',
    tone: params.tone || 'professional',
    language: params.language || 'zh',
  })
}

export interface PromptExportItem {
  name: string
  description?: string | null
  template_type?: string
  content: string
  variables?: string[] | null
  is_active?: boolean
}

export interface PromptExportResponse {
  code: number
  message: string
  data: {
    version: string
    exported_at: string
    count: number
    items: PromptExportItem[]
  }
}

export function exportPrompts(templateType = '') {
  return api.get<PromptExportResponse>('/prompts/export', {
    params: templateType ? { template_type: templateType } : {},
  })
}

export interface PromptImportParams {
  items: PromptExportItem[]
}

export interface PromptImportResult {
  created_count: number
  failed_count: number
  created: Array<{ id: string; name: string }>
  failed: Array<{ index: number; name: string; error: string }>
}

export interface PromptImportResponse {
  code: number
  message: string
  data: PromptImportResult
}

export function importPrompts(items: PromptExportItem[]) {
  return api.post<PromptImportResponse>('/prompts/import', { items })
}
