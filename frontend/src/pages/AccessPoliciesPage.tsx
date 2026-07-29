import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import Modal from '../components/ui/Modal.tsx'
import ConfirmDialog from '../components/ui/ConfirmDialog.tsx'
import Loading from '../components/ui/Loading.tsx'
import EmptyState from '../components/ui/EmptyState.tsx'
import { ICONS } from '../components/ui/Icons.tsx'
import { useCrudResource } from '../hooks/useCrudResource.ts'
import type { AccessPolicy, AccessPolicyForm } from '../types/accessPolicy.ts'
import { EMPTY_POLICY_FORM } from '../types/accessPolicy.ts'

const RESOURCE_TYPES = ['report', 'document', 'audit', 'approval', 'user', 'api_key']
const ACTIONS = ['read', 'write', 'delete', 'export', 'approve']

export default function AccessPoliciesPage() {
  const { t } = useTranslation()

  const {
    items: policies,
    loading,
    error,
    actingId,
    create,
    update,
    remove,
    setError,
    refresh,
  } = useCrudResource<AccessPolicy>({
    baseUrl: '/access-policies',
    pageSize: 100,
    fetchErrorMessage: t('accessPolicies.fetchError'),
    createErrorMessage: t('accessPolicies.createError'),
    updateErrorMessage: t('accessPolicies.updateError'),
    deleteErrorMessage: t('accessPolicies.deleteError'),
    createSuccessMessage: t('accessPolicies.createSuccess'),
    updateSuccessMessage: t('accessPolicies.updateSuccess'),
    deleteSuccessMessage: t('accessPolicies.deleteSuccess'),
  })

  const EFFECT_LABELS: Record<string, string> = {
    allow: t('accessPolicies.effectAllow'),
    deny: t('accessPolicies.effectDeny'),
  }

  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<AccessPolicy | null>(null)
  const [form, setForm] = useState<AccessPolicyForm>({ ...EMPTY_POLICY_FORM })
  const [deleteTarget, setDeleteTarget] = useState<AccessPolicy | null>(null)
  const [keyword, setKeyword] = useState('')

  const conditionsJsonValid = useMemo(() => {
    if (!form.conditions.trim()) return true
    try {
      JSON.parse(form.conditions)
      return true
    } catch {
      return false
    }
  }, [form.conditions])

  // 客户端关键词过滤：按 name / resource_type / action / description 匹配
  const filteredPolicies = useMemo(() => {
    const kw = keyword.trim().toLowerCase()
    if (!kw) return policies
    return policies.filter(
      (p) =>
        (p.name || '').toLowerCase().includes(kw) ||
        (p.resource_type || '').toLowerCase().includes(kw) ||
        (p.action || '').toLowerCase().includes(kw) ||
        (p.description || '').toLowerCase().includes(kw),
    )
  }, [policies, keyword])

  const openCreate = () => {
    setEditing(null)
    setForm({ ...EMPTY_POLICY_FORM })
    setModalOpen(true)
  }

  const openEdit = (policy: AccessPolicy) => {
    setEditing(policy)
    setForm({
      name: policy.name,
      resource_type: policy.resource_type,
      action: policy.action,
      effect: policy.effect,
      priority: policy.priority,
      conditions: policy.conditions ? JSON.stringify(policy.conditions, null, 2) : '',
      description: policy.description || '',
      is_active: policy.is_active,
    })
    setModalOpen(true)
  }

  const handleSubmit = async () => {
    let conditions: Record<string, unknown> | null = null
    if (form.conditions.trim()) {
      try {
        conditions = JSON.parse(form.conditions)
      } catch {
        setError(t('accessPolicies.conditionsMustBeJson'))
        return
      }
    }
    const payload = {
      name: form.name,
      resource_type: form.resource_type,
      action: form.action,
      effect: form.effect,
      priority: form.priority,
      conditions,
      description: form.description || null,
      is_active: form.is_active,
    }
    if (editing) {
      const updated = await update(editing.id, payload)
      if (updated) setModalOpen(false)
    } else {
      const created = await create(payload)
      if (created) setModalOpen(false)
    }
  }

  const handleDelete = async (policy: AccessPolicy) => {
    await remove(policy.id)
  }

  // 行内切换启用状态：复用 update，仅传 is_active 字段
  const toggleActive = async (policy: AccessPolicy) => {
    await update(policy.id, { is_active: !policy.is_active })
  }

  return (
    <div className="container">
      <div className="page-header">
        <div>
          <h1>{t('accessPolicies.title')}</h1>
          <p className="text-muted text-sm">{t('accessPolicies.subtitle')}</p>
        </div>
        <button type="button" onClick={openCreate}>{t('accessPolicies.create')}</button>
      </div>

      {error && (
        <div className="alert alert-error mb-4" role="alert">
          <span>{error}</span>
          <button type="button" className="chat-error-retry" onClick={refresh}>
            {t('accessPolicies.retry')}
          </button>
        </div>
      )}

      {policies.length > 0 && (
        <div className="toolbar">
          <div className="search-inline">
            <ICONS.search size={14} />
            <input
              type="search"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              placeholder={t('accessPolicies.searchPlaceholder')}
              aria-label={t('accessPolicies.searchPlaceholder')}
            />
          </div>
        </div>
      )}

      {loading ? (
        <Loading text={t('accessPolicies.loading')} />
      ) : policies.length === 0 ? (
        <EmptyState
          icon="policies"
          title={t('accessPolicies.emptyTitle')}
          description={t('accessPolicies.emptyDesc')}
          action={
            <button type="button" onClick={openCreate}>{t('accessPolicies.create')}</button>
          }
        />
      ) : filteredPolicies.length === 0 ? (
        <EmptyState
          icon="search"
          title={t('accessPolicies.emptySearchTitle')}
          description={t('accessPolicies.emptySearchDesc')}
        />
      ) : (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>{t('accessPolicies.colName')}</th>
                <th>{t('accessPolicies.colResource')}</th>
                <th>{t('accessPolicies.colAction')}</th>
                <th>{t('accessPolicies.colEffect')}</th>
                <th>{t('accessPolicies.colPriority')}</th>
                <th>{t('accessPolicies.colStatus')}</th>
                <th>{t('accessPolicies.colActions')}</th>
              </tr>
            </thead>
            <tbody>
              {filteredPolicies.map((policy) => (
                <tr key={policy.id}>
                  <td>
                    <div>{policy.name}</div>
                    {policy.description && (
                      <div className="text-muted text-xs">{policy.description}</div>
                    )}
                  </td>
                  <td>{policy.resource_type}</td>
                  <td>{policy.action}</td>
                  <td>
                    <span className={`badge ${policy.effect === 'allow' ? 'approved' : 'rejected'}`}>
                      {EFFECT_LABELS[policy.effect] || policy.effect}
                    </span>
                  </td>
                  <td>{policy.priority}</td>
                  <td>
                    <button
                      type="button"
                      className={`badge ${policy.is_active ? 'approved' : 'draft'}`}
                      onClick={() => toggleActive(policy)}
                      title={t('accessPolicies.toggleStatusHint')}
                    >
                      {policy.is_active ? t('accessPolicies.statusActive') : t('accessPolicies.statusInactive')}
                    </button>
                  </td>
                  <td>
                    <div className="action-group">
                      <button type="button" className="secondary" onClick={() => openEdit(policy)}>
                        {t('accessPolicies.edit')}
                      </button>
                      <button type="button" className="danger" onClick={() => setDeleteTarget(policy)}>
                        {t('accessPolicies.delete')}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {modalOpen && (
        <Modal
          title={editing ? t('accessPolicies.modalTitleEdit') : t('accessPolicies.modalTitleCreate')}
          onClose={() => setModalOpen(false)}
          footer={
            <>
              <button type="button" className="secondary" onClick={() => setModalOpen(false)}>
                {t('accessPolicies.cancel')}
              </button>
              <button
                type="button"
                onClick={handleSubmit}
                disabled={!!actingId || !form.name || !conditionsJsonValid}
              >
                {actingId ? t('accessPolicies.saving') : t('accessPolicies.save')}
              </button>
            </>
          }
        >
          {error && <div className="alert alert-error mb-3">{error}</div>}
          <div className="form-group">
            <label htmlFor="policy-name">{t('accessPolicies.fieldName')}</label>
            <input
              id="policy-name"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder={t('accessPolicies.fieldNamePlaceholder')}
            />
          </div>
          <div className="form-row">
            <div className="form-group">
              <label htmlFor="policy-resource">{t('accessPolicies.fieldResourceType')}</label>
              <select
                id="policy-resource"
                value={form.resource_type}
                onChange={(e) => setForm({ ...form, resource_type: e.target.value })}
              >
                {RESOURCE_TYPES.map((rt) => (
                  <option key={rt} value={rt}>{rt}</option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label htmlFor="policy-action">{t('accessPolicies.fieldAction')}</label>
              <select
                id="policy-action"
                value={form.action}
                onChange={(e) => setForm({ ...form, action: e.target.value })}
              >
                {ACTIONS.map((a) => (
                  <option key={a} value={a}>{a}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="form-row">
            <div className="form-group">
              <label htmlFor="policy-effect">{t('accessPolicies.fieldEffect')}</label>
              <select
                id="policy-effect"
                value={form.effect}
                onChange={(e) =>
                  setForm({ ...form, effect: e.target.value as 'allow' | 'deny' })
                }
              >
                <option value="allow">{t('accessPolicies.effectAllow')}</option>
                <option value="deny">{t('accessPolicies.effectDeny')}</option>
              </select>
            </div>
            <div className="form-group">
              <label htmlFor="policy-priority">{t('accessPolicies.fieldPriority')}</label>
              <input
                id="policy-priority"
                type="number"
                value={form.priority}
                onChange={(e) => setForm({ ...form, priority: Number(e.target.value) })}
              />
            </div>
          </div>
          <div className="form-group">
            <label htmlFor="policy-conditions">{t('accessPolicies.fieldConditions')}</label>
            <textarea
              id="policy-conditions"
              rows={4}
              value={form.conditions}
              onChange={(e) => setForm({ ...form, conditions: e.target.value })}
              placeholder={t('accessPolicies.fieldConditionsPlaceholder')}
              style={!conditionsJsonValid ? { borderColor: 'var(--color-danger)' } : undefined}
            />
            {!conditionsJsonValid && (
              <p style={{ color: 'var(--color-danger)', fontSize: '0.75rem', marginTop: 4 }}>
                {t('accessPolicies.conditionsInvalid')}
              </p>
            )}
          </div>
          <div className="form-group">
            <label htmlFor="policy-desc">{t('accessPolicies.fieldDescription')}</label>
            <input
              id="policy-desc"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              placeholder={t('accessPolicies.fieldDescriptionPlaceholder')}
            />
          </div>
          <div className="form-group">
            <label>
              <input
                type="checkbox"
                checked={form.is_active}
                onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
              />{' '}
              {t('accessPolicies.fieldIsActive')}
            </label>
          </div>
        </Modal>
      )}

      <ConfirmDialog
        open={!!deleteTarget}
        title={t('accessPolicies.confirmDeleteTitle')}
        message={deleteTarget ? <>{t('accessPolicies.confirmDeleteMsg', { name: deleteTarget.name })}</> : null}
        confirmText={t('accessPolicies.confirmDelete')}
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
