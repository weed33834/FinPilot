export interface Report {
  id: string
  title: string
  report_type: string
  status: string
  parameters: Record<string, unknown>
  content: ReportContent | null
  content_url: string | null
  summary: string | null
  error_message: string | null
  template_id: string | null
  created_at: string
}

export interface ReportChartSeries {
  name: string
  metric: string
  data: Array<{ label: string; value: number }>
}

export interface ReportChart {
  type: 'bar' | 'line'
  title: string
  series: ReportChartSeries[]
}

export interface ReportContent {
  title: string
  year: number | null
  period: string
  period_label: string
  sections: Array<{
    name: string
    metric: string
    value: number
  }>
  summary: string
  chart?: ReportChart
}

export interface ReportTemplate {
  id: string
  tenant_id: string
  name: string
  report_type: string
  sections: Array<{ name: string; metric: string }>
  summary_template: string
  title_template: string
  created_by: string | null
  is_active: string
  created_at: string | null
  updated_at: string | null
}

export interface ReportTemplateSection {
  name: string
  metric: string
}

export interface ReportTemplateCreate {
  name: string
  report_type: 'profit' | 'balance' | 'cash' | 'custom' | 'comparison'
  sections: ReportTemplateSection[]
  summary_template: string
  title_template: string
}

export interface ReportTemplateUpdate {
  name?: string
  sections?: ReportTemplateSection[]
  summary_template?: string
  title_template?: string
  is_active?: 'Y' | 'N'
}

export interface PaginatedResponse<T> {
  total: number
  page: number
  page_size: number
  items: T[]
}

export interface DataResponse<T> {
  code: number
  message: string
  data: T
}
