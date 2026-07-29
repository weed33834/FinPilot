import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import Loading from '../components/ui/Loading.tsx'
import EmptyState from '../components/ui/EmptyState.tsx'
import ConfirmDialog from '../components/ui/ConfirmDialog.tsx'
import { ICONS } from '../components/ui/Icons.tsx'
import { api } from '../api/client.ts'
import { getErrorMessage } from '../utils/errors.ts'
import { formatDateTime } from '../utils/format.ts'
import { useCrudResource } from '../hooks/useCrudResource.ts'
import type {
  ReportSubscription,
  ReportSubscriptionCreate,
  ReportSubscriptionUpdate,
  SubscriptionChannel,
  SubscriptionReportType,
  SubscriptionFrequency,
  SubscriptionExportFormat,
} from '../types/reportSubscription.ts'
import {
  CHANNELS,
  EXPORT_FORMATS,
  REPORT_TYPES,
  emptyForm,
  formatFrequency,
  type FormState,
} from './report-subscriptions/constants.ts'
import SubscriptionFormModal from './report-subscriptions/SubscriptionFormModal.tsx'

export default function ReportSubscriptionsPage() {
  const { t } = useTranslation()
  const {
    items: subs,
    loading,
    error,
    actingId,
    refresh,
    create,
    update,
    remove,
    setActingId,
    setError,
  } = useCrudResource<ReportSubscription>({
    baseUrl: '/report-subscriptions',
    fetchErrorMessage: t('reportSubscriptions.loadFailed'),
    createErrorMessage: t('reportSubscriptions.createFailed'),
    updateErrorMessage: t('reportSubscriptions.updateFailed'),
    deleteErrorMessage: t('reportSubscriptions.deleteFailed'),
    createSuccessMessage: t('reportSubscriptions.createSuccess'),
    updateSuccessMessage: t('reportSubscriptions.updateSuccess'),
    deleteSuccessMessage: t('reportSubscriptions.deleteSuccess'),
  })

  const [createOpen, setCreateOpen] = useState(false)
  const [editing, setEditing] = useState<ReportSubscription | null>(null)
  const [form, setForm] = useState<FormState>(emptyForm)
  const [deleteTarget, setDeleteTarget] = useState<ReportSubscription | null>(null)
  const [runTarget, setRunTarget] = useState<ReportSubscription | null>(null)
  const [keyword, setKeyword] = useState('')

  // 客户端关键词过滤（按订阅名称匹配）
  const filteredSubs = useMemo(() => {
    const kw = keyword.trim().toLowerCase()
    if (!kw) return subs
    return subs.filter((s) => (s.name || '').toLowerCase().includes(kw))
  }, [subs, keyword])

  // 将常量列表的 labelKey 经 t() 解析为展示文案，找不到则回退原始值
  const labelFor = (
    list: { value: string; labelKey: string }[],
    value: string,
  ): string => {
    const item = list.find((x) => x.value === value)
    return item ? t(item.labelKey) : value
  }

  const openCreate = () => {
    setForm(emptyForm)
    setEditing(null)
    setCreateOpen(true)
  }

  const openEdit = (sub: ReportSubscription) => {
    const params = sub.parameters as { year?: number; period?: string }
    setForm({
      name: sub.name,
      report_type: (sub.report_type as SubscriptionReportType) || 'profit',
      year: params.year != null ? String(params.year) : '',
      period: params.period || '',
      frequency: (sub.frequency as SubscriptionFrequency) || 'daily',
      at_hour: String(sub.at_hour),
      at_minute: String(sub.at_minute),
      day_of_week: sub.day_of_week != null ? String(sub.day_of_week) : '0',
      day_of_month: sub.day_of_month != null ? String(sub.day_of_month) : '1',
      export_format: (sub.export_format as SubscriptionExportFormat) || 'pdf',
      channels: (sub.channels as SubscriptionChannel[]) || ['in_app'],
      recipients: (sub.recipients || []).join(', '),
    })
    setEditing(sub)
    setCreateOpen(true)
  }

  // 统一构造 create/update payload：update 不含 report_type（创建后不可改）
  const buildPayload = (isUpdate: boolean): ReportSubscriptionCreate | ReportSubscriptionUpdate => {
    const payload: ReportSubscriptionUpdate = {
      name: form.name,
      parameters: {
        ...(form.year && { year: Number(form.year) }),
        ...(form.period && { period: form.period }),
      },
      frequency: form.frequency,
      at_hour: Number(form.at_hour),
      at_minute: Number(form.at_minute),
      export_format: form.export_format,
      channels: form.channels,
      recipients: form.recipients
        .split(',')
        .map((r) => r.trim())
        .filter(Boolean),
    }
    if (form.frequency === 'weekly') {
      payload.day_of_week = Number(form.day_of_week)
    }
    if (form.frequency === 'monthly') {
      payload.day_of_month = Number(form.day_of_month)
    }
    if (isUpdate) {
      return payload
    }
    return { ...payload, report_type: form.report_type } as ReportSubscriptionCreate
  }

  const handleSubmit = async () => {
    if (editing) {
      const payload = buildPayload(true) as ReportSubscriptionUpdate
      const updated = await update(editing.id, payload)
      if (updated) setCreateOpen(false)
    } else {
      const created = await create(buildPayload(false) as ReportSubscriptionCreate)
      if (created) setCreateOpen(false)
    }
  }

  // 行内切换启用状态：复用 update，仅传 is_active 字段
  const handleToggle = async (sub: ReportSubscription) => {
    const next = sub.is_active === 'Y' ? 'N' : 'Y'
    await update(sub.id, { is_active: next })
  }

  // 手动执行是订阅页特有动作，直接调用专用接口，复用 hook 的 actingId/error/refresh
  const handleRun = async (sub: ReportSubscription) => {
    setActingId(sub.id)
    setError('')
    try {
      const response = await api.post(`/report-subscriptions/${sub.id}/run`)
      const result = response.data.data
      if (result?.status === 'failed') {
        setError(
          t('reportSubscriptions.runFailed', {
            error: result.error || t('reportSubscriptions.unknownError'),
          }),
        )
      } else {
        await refresh()
      }
    } catch (err) {
      setError(getErrorMessage(err, t('reportSubscriptions.triggerFailed')))
    } finally {
      setActingId(null)
    }
  }

  const handleDelete = async (sub: ReportSubscription) => {
    await remove(sub.id)
  }

  const toggleChannel = (ch: SubscriptionChannel) => {
    setForm((prev) => ({
      ...prev,
      channels: prev.channels.includes(ch)
        ? prev.channels.filter((c) => c !== ch)
        : [...prev.channels, ch],
    }))
  }

  return (
    <div className="container">
      <div className="page-header">
        <h1>{t('reportSubscriptions.title')}</h1>
        <button type="button" onClick={openCreate}>{t('reportSubscriptions.create')}</button>
      </div>

      {error && (
        <div className="alert alert-error mb-4" role="alert">
          <span>{error}</span>
          <button type="button" className="chat-error-retry" onClick={refresh}>
            {t('reportSubscriptions.retry')}
          </button>
        </div>
      )}

      {subs.length > 0 && (
        <div className="toolbar">
          <div className="search-inline">
            <ICONS.search size={14} />
            <input
              type="search"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              placeholder={t('reportSubscriptions.searchPlaceholder')}
              aria-label={t('reportSubscriptions.searchPlaceholder')}
            />
          </div>
        </div>
      )}

      {loading ? (
        <Loading text={t('reportSubscriptions.loading')} />
      ) : subs.length === 0 ? (
        <EmptyState
          icon="reports"
          title={t('reportSubscriptions.emptyTitle')}
          description={t('reportSubscriptions.emptyDesc')}
          action={
            <button type="button" onClick={openCreate}>{t('reportSubscriptions.create')}</button>
          }
        />
      ) : filteredSubs.length === 0 ? (
        <EmptyState
          icon="search"
          title={t('reportSubscriptions.emptySearchTitle')}
          description={t('reportSubscriptions.emptySearchDesc')}
        />
      ) : (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>{t('reportSubscriptions.colName')}</th>
                <th>{t('reportSubscriptions.colReportType')}</th>
                <th>{t('reportSubscriptions.colSchedule')}</th>
                <th>{t('reportSubscriptions.colExport')}</th>
                <th>{t('reportSubscriptions.colChannels')}</th>
                <th>{t('reportSubscriptions.colStatus')}</th>
                <th>{t('reportSubscriptions.colNextRun')}</th>
                <th>{t('reportSubscriptions.colActions')}</th>
              </tr>
            </thead>
            <tbody>
              {filteredSubs.map((sub) => (
                <tr key={sub.id}>
                  <td>{sub.name}</td>
                  <td>{labelFor(REPORT_TYPES, sub.report_type)}</td>
                  <td>{formatFrequency(sub, t)}</td>
                  <td>{labelFor(EXPORT_FORMATS, sub.export_format)}</td>
                  <td>
                    {sub.channels.length > 0
                      ? sub.channels.map((c) => labelFor(CHANNELS, c)).join(', ')
                      : <span className="text-muted">—</span>}
                  </td>
                  <td>
                    {sub.is_active === 'Y' ? (
                      <span className="badge success">{t('reportSubscriptions.statusActive')}</span>
                    ) : (
                      <span className="badge rejected">{t('reportSubscriptions.statusInactive')}</span>
                    )}
                  </td>
                  <td>
                    {sub.next_run_at
                      ? formatDateTime(sub.next_run_at)
                      : <span className="text-muted">—</span>}
                  </td>
                  <td>
                    <div className="action-group">
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => setRunTarget(sub)}
                        disabled={actingId === sub.id}
                      >
                        {t('reportSubscriptions.run')}
                      </button>
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => openEdit(sub)}
                        disabled={actingId === sub.id}
                      >
                        {t('reportSubscriptions.edit')}
                      </button>
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => handleToggle(sub)}
                        disabled={actingId === sub.id}
                      >
                        {sub.is_active === 'Y' ? t('reportSubscriptions.disable') : t('reportSubscriptions.enable')}
                      </button>
                      <button
                        type="button"
                        className="danger"
                        onClick={() => setDeleteTarget(sub)}
                        disabled={actingId === sub.id}
                      >
                        {t('reportSubscriptions.delete')}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <SubscriptionFormModal
        open={createOpen}
        editing={!!editing}
        form={form}
        setForm={setForm}
        onSubmit={handleSubmit}
        onCancel={() => setCreateOpen(false)}
        submitting={!!actingId}
        toggleChannel={toggleChannel}
        error={createOpen ? error : undefined}
      />

      <ConfirmDialog
        open={!!deleteTarget}
        title={t('reportSubscriptions.confirmDeleteTitle')}
        message={deleteTarget ? <>{t('reportSubscriptions.confirmDeleteMsg', { name: deleteTarget.name })}</> : null}
        confirmText={t('reportSubscriptions.confirmDelete')}
        variant="danger"
        onConfirm={async () => {
          if (deleteTarget) {
            await handleDelete(deleteTarget)
            setDeleteTarget(null)
          }
        }}
        onCancel={() => setDeleteTarget(null)}
      />

      <ConfirmDialog
        open={!!runTarget}
        title={t('reportSubscriptions.confirmRunTitle')}
        message={runTarget ? <>{t('reportSubscriptions.confirmRunMsg', { name: runTarget.name })}</> : null}
        confirmText={t('reportSubscriptions.confirmRun')}
        variant="warning"
        onConfirm={async () => {
          if (runTarget) {
            await handleRun(runTarget)
            setRunTarget(null)
          }
        }}
        onCancel={() => setRunTarget(null)}
      />
    </div>
  )
}
