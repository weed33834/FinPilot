import { useEffect, useState } from 'react'
import { useForm, Controller } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { api } from '../api/client.ts'
import { getErrorMessage } from '../utils/errors.ts'
import type { Report, DataResponse, ReportTemplate } from '../types/report.ts'

interface ReportCreateProps {
  onCreated: (report: Report) => void
}

const PERIODS = [
  { value: 'Q1', label: 'Q1' },
  { value: 'Q2', label: 'Q2' },
  { value: 'Q3', label: 'Q3' },
  { value: 'Q4', label: 'Q4' },
  { value: 'H1', label: 'H1' },
  { value: 'H2', label: 'H2' },
  { value: 'annual', label: '全年' },
]

const REPORT_TYPES = [
  { value: 'profit', label: '利润表' },
  { value: 'balance', label: '资产负债表' },
  { value: 'cash', label: '现金流量表' },
  { value: 'custom', label: '自定义' },
  { value: 'comparison', label: '多期对比' },
]

const createSchema = z.object({
  title: z.string().min(1, '请输入标题'),
  reportType: z.enum(['profit', 'balance', 'cash', 'custom', 'comparison']),
  templateId: z.string(),
  year: z.number(),
  period: z.enum(['Q1', 'Q2', 'Q3', 'Q4', 'H1', 'H2', 'annual']),
})

type CreateForm = z.infer<typeof createSchema>

export default function ReportCreate({ onCreated }: ReportCreateProps) {
  const [years, setYears] = useState<number[]>([new Date().getFullYear() - 1, new Date().getFullYear()])
  const [yearInput, setYearInput] = useState('')
  const [templates, setTemplates] = useState<ReportTemplate[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const {
    register,
    handleSubmit,
    control,
    watch,
    reset,
    formState: { errors },
  } = useForm<CreateForm>({
    resolver: zodResolver(createSchema),
    defaultValues: {
      title: '',
      reportType: 'profit',
      templateId: '',
      year: new Date().getFullYear(),
      period: 'Q2',
    },
  })

  const reportType = watch('reportType')
  const isComparison = reportType === 'comparison'

  const fetchTemplates = async (rtype: string) => {
    try {
      const response = await api.get<DataResponse<{ items: ReportTemplate[] }>>(
        '/report-templates',
        { params: { page: 1, page_size: 50, active_only: true } },
      )
      const items = response.data.data?.items || []
      setTemplates(items.filter((t) => t.report_type === rtype))
    } catch {
      setTemplates([])
    }
  }

  useEffect(() => {
    void fetchTemplates(reportType)
  }, [reportType])

  const addYear = () => {
    const parsed = parseInt(yearInput, 10)
    if (!Number.isNaN(parsed) && !years.includes(parsed)) {
      setYears([...years, parsed].sort((a, b) => a - b))
    }
    setYearInput('')
  }

  const removeYear = (y: number) => {
    setYears(years.filter((v) => v !== y))
  }

  const onSubmit = async (data: CreateForm) => {
    setError('')
    setLoading(true)
    try {
      const parameters: Record<string, unknown> =
        isComparison
          ? { years, period: data.period }
          : { year: data.year, period: data.period }
      const payload: Record<string, unknown> = {
        title: data.title,
        report_type: data.reportType,
        parameters,
      }
      if (data.templateId) {
        payload.template_id = data.templateId
      }
      const response = await api.post<DataResponse<Report>>('/reports', payload)
      if (!response.data.data) return
      onCreated(response.data.data)
      reset()
      setYears([new Date().getFullYear() - 1, new Date().getFullYear()])
    } catch (err) {
      setError(getErrorMessage(err, '创建报告失败'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card">
      <h3 className="card-title">新建报告</h3>
      {error && (
        <div className="alert alert-error mb-4" role="alert">
          {error}
        </div>
      )}
      <form onSubmit={handleSubmit(onSubmit)}>
        <div className="form-group">
          <label htmlFor="report-title">标题</label>
          <input id="report-title" {...register('title')} />
          {errors.title && <span className="text-error text-sm">{errors.title.message}</span>}
        </div>
        <div className="form-row">
          <div className="form-group">
            <label htmlFor="report-type">类型</label>
            <select id="report-type" {...register('reportType')}>
              {REPORT_TYPES.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </div>
          <div className="form-group">
            <label htmlFor="report-template">模板</label>
            <select
              id="report-template"
              {...register('templateId')}
              disabled={templates.length === 0}
            >
              <option value="">默认模板</option>
              {templates.map((t) => (
                <option key={t.id} value={t.id}>{t.name}</option>
              ))}
            </select>
          </div>
        </div>
        {isComparison ? (
          <div className="form-group">
            <label htmlFor="report-year-input">年份（多选）</label>
            <div className="form-row">
              <input
                id="report-year-input"
                type="number"
                value={yearInput}
                onChange={(e) => setYearInput(e.target.value)}
                placeholder="输入年份后回车添加"
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    addYear()
                  }
                }}
              />
              <button type="button" className="secondary" onClick={addYear}>添加</button>
            </div>
            <div className="chips">
              {years.map((y) => (
                <span key={y} className="chip removable">
                  {y}
                  <button
                    type="button"
                    className="chip-remove"
                    onClick={() => removeYear(y)}
                    aria-label={`移除 ${y}`}
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          </div>
        ) : (
          <div className="form-row">
            <div className="form-group">
              <label htmlFor="report-year">年份</label>
              <Controller
                name="year"
                control={control}
                render={({ field }) => (
                  <input
                    id="report-year"
                    type="number"
                    value={field.value}
                    onChange={(e) => {
                      const parsed = parseInt(e.target.value, 10)
                      field.onChange(Number.isNaN(parsed) ? new Date().getFullYear() : parsed)
                    }}
                  />
                )}
              />
            </div>
          </div>
        )}
        <div className="form-group">
          <label htmlFor="report-period">周期</label>
          <select id="report-period" {...register('period')}>
            {PERIODS.map((p) => (
              <option key={p.value} value={p.value}>{p.label}</option>
            ))}
          </select>
        </div>
        <div className="actions">
          <button type="submit" disabled={loading}>
            {loading ? '创建中...' : '创建报告'}
          </button>
        </div>
      </form>
    </div>
  )
}
