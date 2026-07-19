import { useState } from 'react'
import Modal from '../components/ui/Modal.tsx'
import ConfirmDialog from '../components/ui/ConfirmDialog.tsx'
import Loading from '../components/ui/Loading.tsx'
import EmptyState from '../components/ui/EmptyState.tsx'
import { useCrudResource } from '../hooks/useCrudResource.ts'
import { formatDateTime } from '../utils/format.ts'
import type {
  ReportTemplate,
  ReportTemplateCreate,
  ReportTemplateSection,
  ReportTemplateUpdate,
} from '../types/report.ts'

const REPORT_TYPES: { value: ReportTemplateCreate['report_type']; label: string }[] = [
  { value: 'profit', label: '利润表' },
  { value: 'balance', label: '资产负债表' },
  { value: 'cash', label: '现金流量表' },
  { value: 'custom', label: '自定义' },
  { value: 'comparison', label: '多期对比' },
]

// 常用指标预设，便于多选；后端按 metric 字段名取 FinancialReport 数据
const METRIC_PRESETS: { metric: string; name: string }[] = [
  { metric: 'revenue', name: '营业收入' },
  { metric: 'operating_cost', name: '营业成本' },
  { metric: 'operating_profit', name: '营业利润' },
  { metric: 'net_profit', name: '净利润' },
  { metric: 'total_assets', name: '总资产' },
  { metric: 'total_liabilities', name: '总负债' },
  { metric: 'owner_equity', name: '所有者权益' },
  { metric: 'cash_flow_operating', name: '经营活动现金流' },
]

interface FormState {
  name: string
  report_type: ReportTemplateCreate['report_type']
  sections: ReportTemplateSection[]
  summary_template: string
  title_template: string
  is_active: 'Y' | 'N'
}

const emptyForm: FormState = {
  name: '',
  report_type: 'profit',
  sections: [],
  summary_template: '',
  title_template: '',
  is_active: 'Y',
}

export default function ReportTemplatesPage() {
  const {
    items: templates,
    loading,
    error,
    actingId,
    create,
    update,
    remove,
  } = useCrudResource<ReportTemplate>({
    baseUrl: '/report-templates',
    fetchErrorMessage: '加载模板列表失败',
    createErrorMessage: '创建模板失败',
    updateErrorMessage: '更新模板失败',
    deleteErrorMessage: '删除模板失败',
    createSuccessMessage: '模板创建成功',
    updateSuccessMessage: '模板更新成功',
    deleteSuccessMessage: '模板删除成功',
  })

  const [createOpen, setCreateOpen] = useState(false)
  const [editing, setEditing] = useState<ReportTemplate | null>(null)
  const [form, setForm] = useState<FormState>(emptyForm)
  const [deleteTarget, setDeleteTarget] = useState<ReportTemplate | null>(null)

  const openCreate = () => {
    setForm(emptyForm)
    setEditing(null)
    setCreateOpen(true)
  }

  const openEdit = (tpl: ReportTemplate) => {
    setForm({
      name: tpl.name,
      report_type: (tpl.report_type as FormState['report_type']) || 'profit',
      sections: (tpl.sections || []) as ReportTemplateSection[],
      summary_template: tpl.summary_template || '',
      title_template: tpl.title_template || '',
      is_active: (tpl.is_active as 'Y' | 'N') || 'Y',
    })
    setEditing(tpl)
    setCreateOpen(true)
  }

  // 创建载荷：包含 report_type
  const buildPayload = (): ReportTemplateCreate => ({
    name: form.name,
    report_type: form.report_type,
    sections: form.sections,
    summary_template: form.summary_template,
    title_template: form.title_template,
  })

  const handleSubmit = async () => {
    if (editing) {
      // 更新载荷：不含 report_type（创建后不可改），含 is_active
      const payload: ReportTemplateUpdate = {
        name: form.name,
        sections: form.sections,
        summary_template: form.summary_template,
        title_template: form.title_template,
        is_active: form.is_active,
      }
      const updated = await update(editing.id, payload)
      if (updated) setCreateOpen(false)
    } else {
      const created = await create(buildPayload())
      if (created) setCreateOpen(false)
    }
  }

  const handleDelete = async (tpl: ReportTemplate) => {
    await remove(tpl.id)
  }

  // 行内切换启用状态：复用 update，仅传 is_active 字段
  const handleToggle = async (tpl: ReportTemplate) => {
    const next = tpl.is_active === 'Y' ? 'N' : 'Y'
    await update(tpl.id, { is_active: next })
  }

  const toggleMetric = (preset: { metric: string; name: string }) => {
    setForm((prev) => {
      const exists = prev.sections.some((s) => s.metric === preset.metric)
      const sections = exists
        ? prev.sections.filter((s) => s.metric !== preset.metric)
        : [...prev.sections, { name: preset.name, metric: preset.metric }]
      return { ...prev, sections }
    })
  }

  return (
    <div className="container">
      <div className="page-header">
        <h1>报告模板</h1>
        <button type="button" onClick={openCreate}>新建模板</button>
      </div>

      {error && (
        <div className="alert alert-error mb-4" role="alert">
          {error}
        </div>
      )}

      {loading ? (
        <Loading text="加载模板中..." />
      ) : templates.length === 0 ? (
        <EmptyState title="暂无报告模板" description="点击「新建模板」配置自定义标题、摘要与指标 sections。" />
      ) : (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>名称</th>
                <th>报告类型</th>
                <th>sections</th>
                <th>状态</th>
                <th>创建时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {templates.map((tpl) => (
                <tr key={tpl.id}>
                  <td>{tpl.name}</td>
                  <td>{REPORT_TYPES.find((t) => t.value === tpl.report_type)?.label || tpl.report_type}</td>
                  <td>{tpl.sections?.length || 0}</td>
                  <td>
                    {tpl.is_active === 'Y' ? (
                      <span className="badge success">启用</span>
                    ) : (
                      <span className="badge rejected">已停用</span>
                    )}
                  </td>
                  <td>
                    {tpl.created_at
                      ? formatDateTime(tpl.created_at)
                      : <span className="text-muted">—</span>}
                  </td>
                  <td>
                    <div className="action-group">
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => openEdit(tpl)}
                        disabled={actingId === tpl.id}
                      >
                        编辑
                      </button>
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => handleToggle(tpl)}
                        disabled={actingId === tpl.id}
                      >
                        {tpl.is_active === 'Y' ? '停用' : '启用'}
                      </button>
                      <button
                        type="button"
                        className="danger"
                        onClick={() => setDeleteTarget(tpl)}
                        disabled={actingId === tpl.id}
                      >
                        删除
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {createOpen && (
        <Modal
          title={editing ? '编辑模板' : '新建模板'}
          onClose={() => setCreateOpen(false)}
          footer={
            <>
              <button type="button" className="secondary" onClick={() => setCreateOpen(false)}>
                取消
              </button>
              <button type="button" onClick={handleSubmit} disabled={!!actingId || !form.name}>
                {actingId ? '保存中...' : '保存'}
              </button>
            </>
          }
        >
          {error && <div className="alert alert-error mb-3">{error}</div>}
          <div className="form-group">
            <label htmlFor="tpl-name">模板名称</label>
            <input
              id="tpl-name"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="便于识别用途，如「自定义利润表」"
            />
          </div>
          <div className="form-group">
            <label htmlFor="tpl-report-type">报告类型</label>
            <select
              id="tpl-report-type"
              value={form.report_type}
              onChange={(e) =>
                setForm({ ...form, report_type: e.target.value as FormState['report_type'] })
              }
              disabled={!!editing}
            >
              {REPORT_TYPES.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
            {editing && (
              <small className="text-muted">报告类型创建后不可修改</small>
            )}
          </div>
          <div className="form-group">
            <span className="detail-label">sections（指标多选）</span>
            <div className="checkbox-group">
              {METRIC_PRESETS.map((preset) => (
                <label key={preset.metric} className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={form.sections.some((s) => s.metric === preset.metric)}
                    onChange={() => toggleMetric(preset)}
                  />
                  {preset.name}
                </label>
              ))}
            </div>
            {form.sections.length > 0 && (
              <small className="text-muted">
                已选：{form.sections.map((s) => s.name).join('、')}
              </small>
            )}
          </div>
          <div className="form-group">
            <label htmlFor="tpl-title">标题模板</label>
            <input
              id="tpl-title"
              value={form.title_template}
              onChange={(e) => setForm({ ...form, title_template: e.target.value })}
              placeholder="${year}年${period_label}自定义报告（留空用内置）"
            />
            <small className="text-muted">支持 string.Template 语法：${'{year}'} ${'{period_label}'} ${'{revenue}'}</small>
          </div>
          <div className="form-group">
            <label htmlFor="tpl-summary">摘要模板</label>
            <textarea
              id="tpl-summary"
              rows={4}
              value={form.summary_template}
              onChange={(e) => setForm({ ...form, summary_template: e.target.value })}
              placeholder="${year}年${period_label}，营业收入 ${revenue} 元。"
            />
            <small className="text-muted">支持 string.Template 语法，留空用内置摘要</small>
          </div>
        </Modal>
      )}

      <ConfirmDialog
        open={!!deleteTarget}
        title="确认删除"
        message={deleteTarget ? <>确定要删除模板「<strong>{deleteTarget.name}</strong>」吗？关联报告将回退到默认模板。</> : null}
        confirmText="确认删除"
        variant="danger"
        onConfirm={async () => {
          if (deleteTarget) {
            await handleDelete(deleteTarget)
            setDeleteTarget(null)
          }
        }}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  )
}
