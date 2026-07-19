import { useState } from 'react'
import Loading from '../components/ui/Loading.tsx'
import EmptyState from '../components/ui/EmptyState.tsx'
import ConfirmDialog from '../components/ui/ConfirmDialog.tsx'
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
    fetchErrorMessage: '加载订阅列表失败',
    createErrorMessage: '创建订阅失败',
    updateErrorMessage: '更新订阅失败',
    deleteErrorMessage: '删除订阅失败',
    createSuccessMessage: '订阅创建成功',
    updateSuccessMessage: '订阅更新成功',
    deleteSuccessMessage: '订阅删除成功',
  })

  const [createOpen, setCreateOpen] = useState(false)
  const [editing, setEditing] = useState<ReportSubscription | null>(null)
  const [form, setForm] = useState<FormState>(emptyForm)
  const [deleteTarget, setDeleteTarget] = useState<ReportSubscription | null>(null)
  const [runTarget, setRunTarget] = useState<ReportSubscription | null>(null)

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
        setError(`执行失败：${result.error || '未知错误'}`)
      } else {
        await refresh()
      }
    } catch (err) {
      setError(getErrorMessage(err, '触发执行失败'))
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
        <h1>报告订阅</h1>
        <button type="button" onClick={openCreate}>新建订阅</button>
      </div>

      {error && (
        <div className="alert alert-error mb-4" role="alert">
          {error}
        </div>
      )}

      {loading ? (
        <Loading text="加载订阅中..." />
      ) : subs.length === 0 ? (
        <EmptyState title="暂无报告订阅" description="点击「新建订阅」配置定时报告自动生成与推送。" />
      ) : (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>名称</th>
                <th>报告类型</th>
                <th>调度</th>
                <th>导出</th>
                <th>通知渠道</th>
                <th>状态</th>
                <th>下次执行</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {subs.map((sub) => (
                <tr key={sub.id}>
                  <td>{sub.name}</td>
                  <td>{REPORT_TYPES.find((t) => t.value === sub.report_type)?.label || sub.report_type}</td>
                  <td>{formatFrequency(sub)}</td>
                  <td>{EXPORT_FORMATS.find((f) => f.value === sub.export_format)?.label || sub.export_format}</td>
                  <td>
                    {sub.channels.length > 0
                      ? sub.channels.map((c) => CHANNELS.find((ch) => ch.value === c)?.label || c).join(', ')
                      : <span className="text-muted">—</span>}
                  </td>
                  <td>
                    {sub.is_active === 'Y' ? (
                      <span className="badge success">启用</span>
                    ) : (
                      <span className="badge rejected">已停用</span>
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
                        执行
                      </button>
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => openEdit(sub)}
                        disabled={actingId === sub.id}
                      >
                        编辑
                      </button>
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => handleToggle(sub)}
                        disabled={actingId === sub.id}
                      >
                        {sub.is_active === 'Y' ? '停用' : '启用'}
                      </button>
                      <button
                        type="button"
                        className="danger"
                        onClick={() => setDeleteTarget(sub)}
                        disabled={actingId === sub.id}
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
        title="确认删除"
        message={deleteTarget ? <>确定要删除订阅「<strong>{deleteTarget.name}</strong>」吗？此操作不可恢复。</> : null}
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

      <ConfirmDialog
        open={!!runTarget}
        title="确认手动触发"
        message={runTarget ? <>确定要手动触发订阅「<strong>{runTarget.name}</strong>」吗？将立即生成报告并推送通知。</> : null}
        confirmText="确认触发"
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
