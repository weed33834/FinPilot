import { api } from './client'
import type { ApiResponse, PaginatedData } from './types'
import type { Report, ReportTemplate } from '../types/report'

// ==================== 类型定义 ====================

export interface ReportListParams {
  page?: number
  page_size?: number
  status?: string
}

export interface ReportCreatePayload {
  title: string
  report_type: string
  parameters: Record<string, unknown>
  template_id?: string
}

export interface ReportExportResult {
  content_url: string
}

export interface ReportTemplateListParams {
  page?: number
  page_size?: number
  active_only?: boolean
}

// ==================== API 函数 ====================

/** 获取财务报告列表 */
export function listReports(params?: ReportListParams) {
  return api.get<ApiResponse<PaginatedData<Report>>>('/reports', { params })
}

/** 获取单条报告详情 */
export function getReport(id: string) {
  return api.get<ApiResponse<Report>>(`/reports/${id}`)
}

/** 创建财务报告 */
export function createReport(payload: ReportCreatePayload) {
  return api.post<ApiResponse<Report>>('/reports', payload)
}

/** 导出报告为指定格式（pdf / xlsx / markdown / json） */
export function exportReport(id: string, format: string) {
  return api.post<ApiResponse<ReportExportResult>>(`/reports/${id}/export`, {}, {
    params: { format },
  })
}

/** 获取报告模板列表 */
export function listReportTemplates(params?: ReportTemplateListParams) {
  return api.get<ApiResponse<PaginatedData<ReportTemplate>>>('/report-templates', { params })
}
