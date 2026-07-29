import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import Modal from '../components/ui/Modal.tsx'
import ConfirmDialog from '../components/ui/ConfirmDialog.tsx'
import Loading from '../components/ui/Loading.tsx'
import EmptyState from '../components/ui/EmptyState.tsx'
import { ICONS } from '../components/ui/Icons.tsx'
import { useCrudResource } from '../hooks/useCrudResource.ts'
import { formatDateTime } from '../utils/format.ts'
import type {
  ReportTemplate,
  ReportTemplateCreate,
  ReportTemplateSection,
  ReportTemplateUpdate,
} from '../types/report.ts'

const REPORT_TYPES: { value: ReportTemplateCreate['report_type']; labelKey: string }[] = [
  { value: 'profit', labelKey: 'reportTemplates.typeProfit' },
  { value: 'balance', labelKey: 'reportTemplates.typeBalance' },
  { value: 'cash', labelKey: 'reportTemplates.typeCash' },
  { value: 'custom', labelKey: 'reportTemplates.typeCustom' },
  { value: 'comparison', labelKey: 'reportTemplates.typeComparison' },
]

// 常用指标预设，便于多选；后端按 metric 字段名取 FinancialReport 数据
const METRIC_PRESETS: { metric: string; labelKey: string }[] = [
  { metric: 'revenue', labelKey: 'reportTemplates.metricRevenue' },
  { metric: 'operating_cost', labelKey: 'reportTemplates.metricOperatingCost' },
  { metric: 'operating_profit', labelKey: 'reportTemplates.metricOperatingProfit' },
  { metric: 'net_profit', labelKey: 'reportTemplates.metricNetProfit' },
  { metric: 'total_assets', labelKey: 'reportTemplates.metricTotalAssets' },
  { metric: 'total_liabilities', labelKey: 'reportTemplates.metricTotalLiabilities' },
  { metric: 'owner_equity', labelKey: 'reportTemplates.metricOwnerEquity' },
  { metric: 'cash_flow_operating', labelKey: 'reportTemplates.metricCashFlowOperating' },
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
  const { t } = useTranslation()
  const {
    items: templates,
    loading,
    error,
    actingId,
    refresh,
    create,
    update,
    remove,
  } = useCrudResource<ReportTemplate>({
    baseUrl: '/report-templates',
    fetchErrorMessage: t('reportTemplates.loadFailed'),
    createErrorMessage: t('reportTemplates.createFailed'),
    updateErrorMessage: t('reportTemplates.updateFailed'),
    deleteErrorMessage: t('reportTemplates.deleteFailed'),
    createSuccessMessage: t('reportTemplates.createSuccess'),
    updateSuccessMessage: t('reportTemplates.updateSuccess'),
    deleteSuccessMessage: t('reportTemplates.deleteSuccess'),
  })

  const [createOpen, setCreateOpen] = useState(false)
  const [editing, setEditing] = useState<ReportTemplate | null>(null)
  const [form, setForm] = useState<FormState>(emptyForm)
  const [deleteTarget, setDeleteTarget] = useState<ReportTemplate | null>(null)
  const [keyword, setKeyword] = useState('')

  // 客户端关键词过滤（按 name 匹配）
  const filteredTemplates = useMemo(() => {
    const kw = keyword.trim().toLowerCase()
    if (!kw) return templates
    return templates.filter((tpl) => (tpl.name || '').toLowerCase().includes(kw))
  }, [templates, keyword])

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

  const toggleMetric = (preset: { metric: string; labelKey: string }) => {
    setForm((prev) => {
      const exists = prev.sections.some((s) => s.metric === preset.metric)
      const sections = exists
        ? prev.sections.filter((s) => s.metric !== preset.metric)
        : [...prev.sections, { name: t(preset.labelKey), metric: preset.metric }]
      return { ...prev, sections }
    })
  }

  const reportTypeLabel = (value: string) => {
    const found = REPORT_TYPES.find((rt) => rt.value === value)
    return found ? t(found.labelKey) : value
  }

  return (
    <div className="container">
      <div className="page-header">
        <h1>{t('reportTemplates.title')}</h1>
        <button type="button" onClick={openCreate}>{t('reportTemplates.create')}</button>
      </div>

      {error && (
        <div className="alert alert-error mb-4" role="alert">
          <span>{error}</span>
          <button type="button" className="chat-error-retry" onClick={refresh}>
            {t('reportTemplates.retry')}
          </button>
        </div>
      )}

      {templates.length > 0 && (
        <div className="toolbar">
          <div className="search-inline">
            <ICONS.search size={14} />
            <input
              type="search"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              placeholder={t('reportTemplates.searchPlaceholder')}
              aria-label={t('reportTemplates.searchPlaceholder')}
            />
          </div>
        </div>
      )}

      {loading ? (
        <Loading text={t('reportTemplates.loading')} />
      ) : templates.length === 0 ? (
        <EmptyState
          icon="templates"
          title={t('reportTemplates.emptyTitle')}
          description={t('reportTemplates.emptyDesc')}
          action={
            <button type="button" onClick={openCreate}>{t('reportTemplates.create')}</button>
          }
        />
      ) : filteredTemplates.length === 0 ? (
        <EmptyState
          icon="search"
          title={t('reportTemplates.emptySearchTitle')}
          description={t('reportTemplates.emptySearchDesc')}
        />
      ) : (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>{t('reportTemplates.colName')}</th>
                <th>{t('reportTemplates.colType')}</th>
                <th>{t('reportTemplates.colSections')}</th>
                <th>{t('reportTemplates.colStatus')}</th>
                <th>{t('reportTemplates.colCreated')}</th>
                <th>{t('reportTemplates.colActions')}</th>
              </tr>
            </thead>
            <tbody>
              {filteredTemplates.map((tpl) => (
                <tr key={tpl.id}>
                  <td>{tpl.name}</td>
                  <td>{reportTypeLabel(tpl.report_type)}</td>
                  <td>{tpl.sections?.length || 0}</td>
                  <td>
                    {tpl.is_active === 'Y' ? (
                      <span className="badge success">{t('reportTemplates.statusActive')}</span>
                    ) : (
                      <span className="badge rejected">{t('reportTemplates.statusInactive')}</span>
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
                        {t('reportTemplates.edit')}
                      </button>
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => handleToggle(tpl)}
                        disabled={actingId === tpl.id}
                      >
                        {tpl.is_active === 'Y' ? t('reportTemplates.disable') : t('reportTemplates.enable')}
                      </button>
                      <button
                        type="button"
                        className="danger"
                        onClick={() => setDeleteTarget(tpl)}
                        disabled={actingId === tpl.id}
                      >
                        {t('reportTemplates.delete')}
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
          title={editing ? t('reportTemplates.editTitle') : t('reportTemplates.createTitle')}
          onClose={() => setCreateOpen(false)}
          footer={
            <>
              <button type="button" className="secondary" onClick={() => setCreateOpen(false)}>
                {t('reportTemplates.cancel')}
              </button>
              <button type="button" onClick={handleSubmit} disabled={!!actingId || !form.name}>
                {actingId ? t('reportTemplates.saving') : t('reportTemplates.save')}
              </button>
            </>
          }
        >
          {error && <div className="alert alert-error mb-3">{error}</div>}
          <div className="form-group">
            <label htmlFor="tpl-name">{t('reportTemplates.name')}</label>
            <input
              id="tpl-name"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder={t('reportTemplates.namePlaceholder')}
            />
          </div>
          <div className="form-group">
            <label htmlFor="tpl-report-type">{t('reportTemplates.reportType')}</label>
            <select
              id="tpl-report-type"
              value={form.report_type}
              onChange={(e) =>
                setForm({ ...form, report_type: e.target.value as FormState['report_type'] })
              }
              disabled={!!editing}
            >
              {REPORT_TYPES.map((rt) => (
                <option key={rt.value} value={rt.value}>{t(rt.labelKey)}</option>
              ))}
            </select>
            {editing && (
              <small className="text-muted">{t('reportTemplates.reportTypeLocked')}</small>
            )}
          </div>
          <div className="form-group">
            <span className="detail-label">{t('reportTemplates.sectionsLabel')}</span>
            <div className="checkbox-group">
              {METRIC_PRESETS.map((preset) => (
                <label key={preset.metric} className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={form.sections.some((s) => s.metric === preset.metric)}
                    onChange={() => toggleMetric(preset)}
                  />
                  {t(preset.labelKey)}
                </label>
              ))}
            </div>
            {form.sections.length > 0 && (
              <small className="text-muted">
                {t('reportTemplates.sectionsSelected', { sections: form.sections.map((s) => s.name).join(', ') })}
              </small>
            )}
          </div>
          <div className="form-group">
            <label htmlFor="tpl-title">{t('reportTemplates.titleTemplate')}</label>
            <input
              id="tpl-title"
              value={form.title_template}
              onChange={(e) => setForm({ ...form, title_template: e.target.value })}
              placeholder={t('reportTemplates.titleTemplatePlaceholder')}
            />
            <small className="text-muted">{t('reportTemplates.titleTemplateHint')}</small>
          </div>
          <div className="form-group">
            <label htmlFor="tpl-summary">{t('reportTemplates.summaryTemplate')}</label>
            <textarea
              id="tpl-summary"
              rows={4}
              value={form.summary_template}
              onChange={(e) => setForm({ ...form, summary_template: e.target.value })}
              placeholder={t('reportTemplates.summaryTemplatePlaceholder')}
            />
            <small className="text-muted">{t('reportTemplates.summaryTemplateHint')}</small>
          </div>
        </Modal>
      )}

      <ConfirmDialog
        open={!!deleteTarget}
        title={t('reportTemplates.confirmDeleteTitle')}
        message={deleteTarget ? <>{t('reportTemplates.confirmDeleteMsg', { name: deleteTarget.name })}</> : null}
        confirmText={t('reportTemplates.confirmDelete')}
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
