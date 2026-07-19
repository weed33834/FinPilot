import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import Modal from '../components/ui/Modal.tsx'
import ConfirmDialog from '../components/ui/ConfirmDialog.tsx'
import Loading from '../components/ui/Loading.tsx'
import EmptyState from '../components/ui/EmptyState.tsx'
import PasswordStrength from '../components/ui/PasswordStrength.tsx'
import { api } from '../api/client.ts'
import { getErrorMessage } from '../utils/errors.ts'
import { formatDateTime } from '../utils/format.ts'
import { useCrudResource } from '../hooks/useCrudResource.ts'
import { useAuth } from '../context/AuthContext.tsx'
import { toast } from '../components/ui/Toaster.tsx'
import type { User } from '../types/user.ts'

const ROLE_LABELS: Record<string, string> = {
  admin: '管理员',
  finance_manager: '财务经理',
  auditor: '审计员',
  viewer: '查看者',
}

const userSchema = z.object({
  username: z.string().min(1, '请输入用户名'),
  email: z.string().email('邮箱格式不正确').or(z.literal('')).optional(),
  password: z.string().min(8, '密码至少 8 位').or(z.literal('')),
  role: z.enum(['admin', 'finance_manager', 'auditor', 'viewer']),
  is_active: z.enum(['Y', 'N']),
})

type UserForm = z.infer<typeof userSchema>

export default function UsersPage() {
  const { userId, username: currentUsername } = useAuth()

  const {
    items: users,
    loading,
    error,
    actingId,
    create,
    update,
    remove,
    setError,
  } = useCrudResource<User>({
    baseUrl: '/users',
    fetchErrorMessage: '加载用户列表失败',
    createErrorMessage: '保存用户失败',
    updateErrorMessage: '保存用户失败',
    deleteErrorMessage: '删除用户失败',
    createSuccessMessage: '用户创建成功',
    updateSuccessMessage: '用户信息已更新',
    deleteSuccessMessage: '用户已删除',
  })

  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<User | null>(null)
  const [resetTarget, setResetTarget] = useState<User | null>(null)
  const [resetPassword, setResetPassword] = useState('')
  const [resetSubmitting, setResetSubmitting] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<User | null>(null)
  const [passwordValue, setPasswordValue] = useState('')


  const {
    register,
    handleSubmit,
    reset: resetForm,
    formState: { errors: formErrors },
  } = useForm<UserForm>({
    resolver: zodResolver(userSchema),
    defaultValues: {
      username: '',
      email: '',
      password: '',
      role: 'viewer',
      is_active: 'Y',
    },
  })

  const openCreate = () => {
    setEditing(null)
    setError('')
    setPasswordValue('')
    resetForm({
      username: '',
      email: '',
      password: '',
      role: 'viewer',
      is_active: 'Y',
    })
    setModalOpen(true)
  }

  const openEdit = (user: User) => {
    setEditing(user)
    setError('')
    setPasswordValue('')
    resetForm({
      username: user.username,
      email: user.email || '',
      password: '',
      role: user.role as UserForm['role'],
      is_active: user.is_active as UserForm['is_active'],
    })
    setModalOpen(true)
  }

  const onSubmit = async (data: UserForm) => {
    if (editing) {
      const payload: Record<string, string> = {
        email: data.email || '',
        role: data.role,
        is_active: data.is_active,
      }
      if (data.password) {
        payload.password = data.password
      }
      const updated = await update(editing.id, payload)
      if (updated) setModalOpen(false)
    } else {
      const created = await create({
        username: data.username,
        email: data.email || null,
        password: data.password,
        role: data.role,
        is_active: data.is_active,
      })
      if (created) setModalOpen(false)
    }
  }

  const handleDelete = async (user: User) => {
    // 自删保护：不能删除自己
    if (userId && user.id === userId) {
      toast.warning('无法删除当前登录账号', '请使用其他管理员账号来删除此用户。')
      setDeleteTarget(null)
      return
    }
    if (currentUsername && user.username === currentUsername) {
      toast.warning('无法删除当前登录账号')
      setDeleteTarget(null)
      return
    }
    await remove(user.id)
    setDeleteTarget(null)
  }

  const handleResetPassword = async () => {
    if (!resetTarget) return
    if (resetPassword.length < 8) {
      setError('密码至少 8 位')
      return
    }
    setResetSubmitting(true)
    setError('')
    try {
      await api.post(`/users/${resetTarget.id}/reset-password`, {
        password: resetPassword,
      })
      toast.success('密码已重置', `用户「${resetTarget.username}」的密码已更新。`)
      setResetTarget(null)
      setResetPassword('')
    } catch (err) {
      const msg = getErrorMessage(err, '重置密码失败')
      setError(msg)
      toast.error(msg)
    } finally {
      setResetSubmitting(false)
    }
  }

  const renderFieldError = (field: keyof UserForm) =>
    formErrors[field] && <span className="text-error text-sm">{formErrors[field]?.message}</span>

  return (
    <div className="container">
      <div className="page-header">
        <h1>用户管理</h1>
        <button type="button" onClick={openCreate}>新建用户</button>
      </div>

      {error && (
        <div className="alert alert-error mb-4" role="alert">
          {error}
        </div>
      )}

      {loading ? (
        <Loading text="加载用户中..." />
      ) : users.length === 0 ? (
        <EmptyState title="暂无用户" description="点击「新建用户」创建第一个用户。" />
      ) : (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>用户名</th>
                <th>邮箱</th>
                <th>角色</th>
                <th>状态</th>
                <th>创建时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.id}>
                  <td>{user.username}</td>
                  <td>{user.email || <span className="text-muted">—</span>}</td>
                  <td>{ROLE_LABELS[user.role] || user.role}</td>
                  <td>
                    {user.is_active === 'Y' ? (
                      <span className="badge success">启用</span>
                    ) : (
                      <span className="badge rejected">禁用</span>
                    )}
                  </td>
                  <td>
                    {formatDateTime(user.created_at)}
                  </td>
                  <td>
                    <div className="action-group">
                      <button type="button" className="secondary" onClick={() => openEdit(user)}>
                        编辑
                      </button>
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => {
                          setResetTarget(user)
                          setResetPassword('')
                        }}
                      >
                        重置密码
                      </button>
                      <button type="button" className="danger" onClick={() => setDeleteTarget(user)}>
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
          title={editing ? '编辑用户' : '新建用户'}
          onClose={() => {
            setError('')
            setModalOpen(false)
          }}
          footer={
            <>
              <button
                type="button"
                className="secondary"
                onClick={() => {
                  setError('')
                  setModalOpen(false)
                }}
              >
                取消
              </button>
              <button type="button" onClick={handleSubmit(onSubmit)} disabled={!!actingId}>
                {actingId ? '保存中...' : '保存'}
              </button>
            </>
          }
        >
          {error && <div className="alert alert-error mb-3">{error}</div>}
          <div className="form-group">
            <label htmlFor="user-username">用户名</label>
            <input
              id="user-username"
              {...register('username')}
              disabled={!!editing}
              placeholder="登录用户名"
            />
            {renderFieldError('username')}
          </div>
          <div className="form-group">
            <label htmlFor="user-email">邮箱</label>
            <input
              id="user-email"
              type="email"
              {...register('email')}
              placeholder="可选"
            />
            {renderFieldError('email')}
          </div>
          <div className="form-group">
            <label htmlFor="user-password">
              {editing ? '新密码（留空保持不变）' : '密码'}
            </label>
            <input
              id="user-password"
              type="password"
              {...register('password', {
                onChange: (e) => setPasswordValue(e.target.value),
              })}
              placeholder={editing ? '留空则不修改' : '至少 8 位'}
              aria-invalid={!!formErrors.password}
            />
            {renderFieldError('password')}
            <PasswordStrength password={passwordValue} />
          </div>
          <div className="form-group">
            <label htmlFor="user-role">角色</label>
            <select id="user-role" {...register('role')}>
              {Object.entries(ROLE_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>
          <div className="form-group">
            <label htmlFor="user-active">状态</label>
            <select id="user-active" {...register('is_active')}>
              <option value="Y">启用</option>
              <option value="N">禁用</option>
            </select>
          </div>
        </Modal>
      )}

      {resetTarget && (
        <Modal
          title={`重置密码 - ${resetTarget.username}`}
          onClose={() => {
            setError('')
            setResetTarget(null)
          }}
          footer={
            <>
              <button
                type="button"
                className="secondary"
                onClick={() => {
                  setError('')
                  setResetTarget(null)
                }}
              >
                取消
              </button>
              <button
                type="button"
                onClick={handleResetPassword}
                disabled={resetSubmitting || resetPassword.length < 8}
              >
                {resetSubmitting ? '重置中...' : '确认重置'}
              </button>
            </>
          }
        >
          {error && <div className="alert alert-error mb-3">{error}</div>}
          <div className="form-group">
            <label htmlFor="reset-password-input">新密码</label>
            <input
              id="reset-password-input"
              type="password"
              value={resetPassword}
              onChange={(e) => setResetPassword(e.target.value)}
              placeholder="至少 8 位"
            />
            <PasswordStrength password={resetPassword} />
          </div>
        </Modal>
      )}

      <ConfirmDialog
        open={!!deleteTarget}
        title="确认删除用户"
        message={
          deleteTarget ? (
            <>
              确定要删除用户「<strong>{deleteTarget.username}</strong>」吗？
              <br />
              <span style={{ color: 'var(--color-text-muted)', fontSize: '0.8125rem' }}>
                此操作不可恢复，该用户的所有数据将被永久清除。
              </span>
            </>
          ) : null
        }
        confirmText="确认删除"
        variant="danger"
        onConfirm={async () => {
          if (deleteTarget) {
            await handleDelete(deleteTarget)
          }
        }}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  )
}
