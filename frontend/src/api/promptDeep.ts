import { api } from './client'

/**
 * 提示词进阶 API 客户端
 *  - 版本历史：/api/v1/prompts/{template_id}/versions
 *  - A/B 测试：/api/v1/prompt-ab-tests
 *  - Few-shot 示例：/api/v1/prompt-few-shot
 */

/* ---------------- 版本历史 ---------------- */

export interface PromptVersionItem {
  id: string
  version: number
  content: string
  change_description?: string | null
  is_active?: boolean
  created_by?: string | null
  created_at?: string | null
  [k: string]: unknown
}

export interface VersionDiffResult {
  version: number
  version_content: string
  current_content: string
  diff: string
  [k: string]: unknown
}

export interface VersionListResponse {
  code: number
  message: string
  data: PromptVersionItem[]
}
export interface VersionSingleResponse {
  code: number
  message: string
  data: PromptVersionItem
}
export interface VersionDiffResponse {
  code: number
  message: string
  data: VersionDiffResult
}
export interface RollbackResponse {
  code: number
  message: string
  data: { id: string; name: string; content: string; rolled_back_to: number }
}

/** 版本列表 */
export function listVersions(templateId: string) {
  return api.get<VersionListResponse>(`/prompts/${templateId}/versions`)
}

/** 创建新版本 */
export function createVersion(
  templateId: string,
  payload: { content: string; change_description?: string; variables?: string[] | null },
) {
  return api.post<VersionSingleResponse>(`/prompts/${templateId}/versions`, payload)
}

/** 回滚到指定版本 */
export function rollbackVersion(templateId: string, version: number) {
  return api.post<RollbackResponse>(`/prompts/${templateId}/versions/${version}/rollback`)
}

/** 对比指定版本与当前内容差异 */
export function diffVersion(templateId: string, version: number) {
  return api.get<VersionDiffResponse>(`/prompts/${templateId}/versions/${version}/diff`)
}

/* ---------------- A/B 测试 ---------------- */

export interface ABTestItem {
  id: string
  name: string
  prompt_key: string
  variant_a_id: string
  variant_b_id: string
  traffic_split_b: number
  status: string
  created_at?: string | null
  updated_at?: string | null
  [k: string]: unknown
}

export interface ABTestListResponse {
  code: number
  message: string
  data: { total: number; page: number; page_size: number; items: ABTestItem[] }
}
export interface ABTestSingleResponse {
  code: number
  message: string
  data: ABTestItem
}
export interface ABTestResultsResponse {
  code: number
  message: string
  data: Record<string, unknown>
}

export interface ABTestCreatePayload {
  name: string
  prompt_key: string
  variant_a_id: string
  variant_b_id: string
  traffic_split_b: number
}

/** 创建 A/B 测试 */
export function createABTest(payload: ABTestCreatePayload) {
  return api.post<ABTestSingleResponse>('/prompt-ab-tests', payload)
}

/** A/B 测试列表 */
export function listABTests(params: { status?: string; prompt_key?: string; page?: number; page_size?: number } = {}) {
  return api.get<ABTestListResponse>('/prompt-ab-tests', {
    params: {
      status: params.status || '',
      prompt_key: params.prompt_key || '',
      page: params.page ?? 1,
      page_size: params.page_size ?? 20,
    },
  })
}

/** A/B 测试详情 */
export function getABTest(testId: string) {
  return api.get<ABTestSingleResponse>(`/prompt-ab-tests/${testId}`)
}

/** 启动 A/B 测试 */
export function startABTest(testId: string) {
  return api.post<ABTestSingleResponse>(`/prompt-ab-tests/${testId}/start`)
}

/** 停止 A/B 测试 */
export function stopABTest(testId: string) {
  return api.post<ABTestSingleResponse>(`/prompt-ab-tests/${testId}/stop`)
}

/** 提交反馈 */
export function submitABTestFeedback(
  testId: string,
  payload: { variant: string; score: number; comment?: string },
) {
  return api.post<{ code: number; message: string; data: unknown }>(
    `/prompt-ab-tests/${testId}/feedback`,
    payload,
  )
}

/** A/B 测试结果 */
export function getABTestResults(testId: string) {
  return api.get<ABTestResultsResponse>(`/prompt-ab-tests/${testId}/results`)
}

/* ---------------- Few-shot 示例 ---------------- */

export interface FewShotExample {
  id: string
  prompt_key: string
  input_text: string
  output_text: string
  category?: string | null
  quality_score?: number
  is_active?: boolean
  display_order?: number
  created_at?: string | null
  [k: string]: unknown
}

export interface FewShotListResponse {
  code: number
  message: string
  data: FewShotExample[]
}
export interface FewShotSingleResponse {
  code: number
  message: string
  data: FewShotExample
}

export interface FewShotCreatePayload {
  prompt_key: string
  input_text: string
  output_text: string
  category?: string
  quality_score?: number
  is_active?: boolean
  display_order?: number
}
export type FewShotUpdatePayload = Partial<FewShotCreatePayload>

/** few-shot 示例列表 */
export function listFewShot(promptKey: string, isActive?: string) {
  return api.get<FewShotListResponse>(`/prompt-few-shot/${encodeURIComponent(promptKey)}`, {
    params: { is_active: isActive || '' },
  })
}

/** 创建 few-shot 示例 */
export function createFewShot(payload: FewShotCreatePayload) {
  return api.post<FewShotSingleResponse>('/prompt-few-shot', payload)
}

/** 更新 few-shot 示例 */
export function updateFewShot(exampleId: string, payload: FewShotUpdatePayload) {
  return api.put<FewShotSingleResponse>(`/prompt-few-shot/${exampleId}`, payload)
}

/** 删除 few-shot 示例 */
export function deleteFewShot(exampleId: string) {
  return api.delete<{ code: number; message: string; data: null }>(`/prompt-few-shot/${exampleId}`)
}

/** 重新排序 few-shot 示例 */
export function reorderFewShot(promptKey: string, exampleIds: string[]) {
  return api.post<FewShotListResponse>('/prompt-few-shot/reorder', {
    prompt_key: promptKey,
    example_ids: exampleIds,
  })
}
