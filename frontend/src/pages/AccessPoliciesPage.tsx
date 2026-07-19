import { useMemo, useState } from 'react'
import Modal from '../components/ui/Modal.tsx'
import ConfirmDialog from '../components/ui/ConfirmDialog.tsx'
import Loading from '../components/ui/Loading.tsx'
import EmptyState from '../components/ui/EmptyState.tsx'
import { useCrudResource } from '../hooks/useCrudResource.ts'
import type { AccessPolicy, AccessPolicyForm } from '../types/accessPolicy.ts'
import { EMPTY_POLICY_FORM } from '../types/accessPolicy.ts'

const EFFECT_LABELS: Record<string, string> = {
  allow: '允许',
  deny: '拒绝',
}

const RESOURCE_TYPES = ['report', 'document', 'audit', 'approval', 'user', 'api_key']
const ACTIONS = ['read', 'write', 'delete', 'export', 'approve']

export default function AccessPoliciesPage() {
  const {
    items: policies,
    loading,
    error,
    actingId,
    create,
    update,
    remove,
    setError,
  } = useCrudResource<AccessPolicy>({
    baseUrl: '/access-policies',
    pageSize: 100,
    fetchErrorMessage: '加载访问策略失败',
    createErrorMessage: '保存策略失败',
    updateErrorMessage: '保存策略失败',
    deleteErrorMessage: '删除策略失败',
    createSuccessMessage: '策略创建成功',
    updateSuccessMessage: '策略更新成功',
    deleteSuccessMessage: '策略删除成功',
  })

  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<AccessPolicy | null>(null)
  const [form, setForm] = useState<AccessPolicyForm>({ ...EMPTY_POLICY_FORM })
  const [deleteTarget, setDeleteTarget] = useState<AccessPolicy | null>(null)

  const conditionsJsonValid = useMemo(() => {
    if (!form.conditions.trim()) return true
    try {
      JSON.parse(form.conditions)
      return true
    } catch {
      return false
    }
  }, [form.conditions])

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
        setError('conditions 必须是合法的 JSON')
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
          <h1>访问策略</h1>
          <p className="text-muted text-sm">基于资源类型与动作的 ABAC 策略，优先级数字越小越先匹配</p>
        </div>
        <button type="button" onClick={openCreate}>新建策略</button>
      </div>

      {error && (
        <div className="alert alert-error mb-4" role="alert">
          {error}
        </div>
      )}

      {loading ? (
        <Loading text="加载策略中..." />
      ) : policies.length === 0 ? (
        <EmptyState title="暂无策略" description="点击「新建策略」配置第一条访问策略。" />
      ) : (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>名称</th>
                <th>资源</th>
                <th>动作</th>
                <th>效果</th>
                <th>优先级</th>
                <th>状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {policies.map((policy) => (
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
                      title="点击切换"
                    >
                      {policy.is_active ? '启用' : '停用'}
                    </button>
                  </td>
                  <td>
                    <div className="action-group">
                      <button type="button" className="secondary" onClick={() => openEdit(policy)}>
                        编辑
                      </button>
                      <button type="button" className="danger" onClick={() => setDeleteTarget(policy)}>
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

      {modalOpen && (
        <Modal
          title={editing ? '编辑策略' : '新建策略'}
          onClose={() => setModalOpen(false)}
          footer={
            <>
              <button type="button" className="secondary" onClick={() => setModalOpen(false)}>
                取消
              </button>
              <button
                type="button"
                onClick={handleSubmit}
                disabled={!!actingId || !form.name || !conditionsJsonValid}
              >
                {actingId ? '保存中...' : '保存'}
              </button>
            </>
          }
        >
          {error && <div className="alert alert-error mb-3">{error}</div>}
          <div className="form-group">
            <label htmlFor="policy-name">名称</label>
            <input
              id="policy-name"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="如：finance_manager 仅可读报告"
            />
          </div>
          <div className="form-row">
            <div className="form-group">
              <label htmlFor="policy-resource">资源类型</label>
              <select
                id="policy-resource"
                value={form.resource_type}
                onChange={(e) => setForm({ ...form, resource_type: e.target.value })}
              >
                {RESOURCE_TYPES.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label htmlFor="policy-action">动作</label>
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
              <label htmlFor="policy-effect">效果</label>
              <select
                id="policy-effect"
                value={form.effect}
                onChange={(e) =>
                  setForm({ ...form, effect: e.target.value as 'allow' | 'deny' })
                }
              >
                <option value="allow">允许</option>
                <option value="deny">拒绝</option>
              </select>
            </div>
            <div className="form-group">
              <label htmlFor="policy-priority">优先级（数字越小越先匹配）</label>
              <input
                id="policy-priority"
                type="number"
                value={form.priority}
                onChange={(e) => setForm({ ...form, priority: Number(e.target.value) })}
              />
            </div>
          </div>
          <div className="form-group">
            <label htmlFor="policy-conditions">条件（JSON，可空）</label>
            <textarea
              id="policy-conditions"
              rows={4}
              value={form.conditions}
              onChange={(e) => setForm({ ...form, conditions: e.target.value })}
              placeholder='{"role": "auditor"}'
              style={!conditionsJsonValid ? { borderColor: 'var(--color-danger)' } : undefined}
            />
            {!conditionsJsonValid && (
              <p style={{ color: 'var(--color-danger)', fontSize: '0.75rem', marginTop: 4 }}>
                JSON 格式不正确，请检查语法
              </p>
            )}
          </div>
          <div className="form-group">
            <label htmlFor="policy-desc">描述</label>
            <input
              id="policy-desc"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              placeholder="可选"
            />
          </div>
          <div className="form-group">
            <label>
              <input
                type="checkbox"
                checked={form.is_active}
                onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
              />{' '}
              启用
            </label>
          </div>
        </Modal>
      )}

      <ConfirmDialog
        open={!!deleteTarget}
        title="确认删除"
        message={deleteTarget ? <>确定要删除策略「<strong>{deleteTarget.name}</strong>」吗？</> : null}
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
