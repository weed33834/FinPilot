import { useMemo, useState } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { useTranslation } from 'react-i18next'
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

// 角色选项（与 zod enum 对齐）。标签走 i18n common:role.* 动态翻译。
const ROLE_OPTIONS = ['admin', 'finance_manager', 'auditor', 'viewer'] as const

type UserForm = z.infer<typeof userSchemaShape>

// zod schema 形状（message 占位 key，渲染前在组件内用 t() 重建带本地化消息的 schema）
const userSchemaShape = z.object({
  username: z.string().min(1, 'users:errUsernameRequired'),
  email: z.string().email('users:errEmailInvalid').or(z.literal('')).optional(),
  password: z.string().min(8, 'users:errPasswordMin').or(z.literal('')),
  role: z.enum(ROLE_OPTIONS),
  is_active: z.enum(['Y', 'N']),
})

export default function UsersPage() {
  const { t } = useTranslation('common')
  const roleLabel = (role: string) => t(`role.${role}`, { defaultValue: role })
  const { userId, username: currentUsername } = useAuth()

  // 组件内用 i18n 文案重建 schema（消息本地化）
  const userSchema = useMemo(
    () =>
      z.object({
        username: z.string().min(1, t('users:errUsernameRequired')),
        email: z.string().email(t('users:errEmailInvalid')).or(z.literal('')).optional(),
        password: z.string().min(8, t('users:errPasswordMin')).or(z.literal('')),
        role: z.enum(ROLE_OPTIONS),
        is_active: z.enum(['Y', 'N']),
      }),
    [t],
  )

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
    fetchErrorMessage: t('users:loadFailed'),
    createErrorMessage: t('users:saveFailed'),
    updateErrorMessage: t('users:saveFailed'),
    deleteErrorMessage: t('users:deleteFailed'),
    createSuccessMessage: t('users:createSuccess'),
    updateSuccessMessage: t('users:updateSuccess'),
    deleteSuccessMessage: t('users:deleteSuccess'),
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
      toast.warning(t('users:cannotDeleteSelf'), t('users:cannotDeleteSelfTip'))
      setDeleteTarget(null)
      return
    }
    if (currentUsername && user.username === currentUsername) {
      toast.warning(t('users:cannotDeleteSelf'))
      setDeleteTarget(null)
      return
    }
    await remove(user.id)
    setDeleteTarget(null)
  }

  const handleResetPassword = async () => {
    if (!resetTarget) return
    if (resetPassword.length < 8) {
      setError(t('users:passwordMinLength'))
      return
    }
    setResetSubmitting(true)
    setError('')
    try {
      await api.post(`/users/${resetTarget.id}/reset-password`, {
        password: resetPassword,
      })
      toast.success(
        t('users:passwordReset'),
        t('users:passwordResetDesc', { username: resetTarget.username }),
      )
      setResetTarget(null)
      setResetPassword('')
    } catch (err) {
      const msg = getErrorMessage(err, t('users:resetFailed'))
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
        <h1>{t('users:title')}</h1>
        <button type="button" onClick={openCreate}>{t('users:create')}</button>
      </div>

      {error && (
        <div className="alert alert-error mb-4" role="alert">
          {error}
        </div>
      )}

      {loading ? (
        <Loading text={t('users:loading')} />
      ) : users.length === 0 ? (
        <EmptyState title={t('users:emptyTitle')} description={t('users:emptyDesc')} />
      ) : (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>{t('users:colUsername')}</th>
                <th>{t('users:colEmail')}</th>
                <th>{t('users:colRole')}</th>
                <th>{t('users:colStatus')}</th>
                <th>{t('users:colCreated')}</th>
                <th>{t('users:colActions')}</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.id}>
                  <td>{user.username}</td>
                  <td>{user.email || <span className="text-muted">—</span>}</td>
                  <td>{roleLabel(user.role)}</td>
                  <td>
                    {user.is_active === 'Y' ? (
                      <span className="badge success">{t('users:statusActive')}</span>
                    ) : (
                      <span className="badge rejected">{t('users:statusInactive')}</span>
                    )}
                  </td>
                  <td>
                    {formatDateTime(user.created_at)}
                  </td>
                  <td>
                    <div className="action-group">
                      <button type="button" className="secondary" onClick={() => openEdit(user)}>
                        {t('users:edit')}
                      </button>
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => {
                          setResetTarget(user)
                          setResetPassword('')
                        }}
                      >
                        {t('users:resetPassword')}
                      </button>
                      <button type="button" className="danger" onClick={() => setDeleteTarget(user)}>
                        {t('users:delete')}
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
          title={editing ? t('users:editTitle') : t('users:createTitle')}
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
                {t('users:cancel')}
              </button>
              <button type="button" onClick={handleSubmit(onSubmit)} disabled={!!actingId}>
                {actingId ? t('users:saving') : t('users:save')}
              </button>
            </>
          }
        >
          {error && <div className="alert alert-error mb-3">{error}</div>}
          <div className="form-group">
            <label htmlFor="user-username">{t('users:username')}</label>
            <input
              id="user-username"
              {...register('username')}
              disabled={!!editing}
              placeholder={t('users:usernamePlaceholder')}
            />
            {renderFieldError('username')}
          </div>
          <div className="form-group">
            <label htmlFor="user-email">{t('users:email')}</label>
            <input
              id="user-email"
              type="email"
              {...register('email')}
              placeholder={t('users:emailPlaceholder')}
            />
            {renderFieldError('email')}
          </div>
          <div className="form-group">
            <label htmlFor="user-password">
              {editing ? t('users:passwordEditLabel') : t('users:password')}
            </label>
            <input
              id="user-password"
              type="password"
              {...register('password', {
                onChange: (e) => setPasswordValue(e.target.value),
              })}
              placeholder={editing ? t('users:passwordEditPlaceholder') : t('users:passwordPlaceholder')}
              aria-invalid={!!formErrors.password}
            />
            {renderFieldError('password')}
            <PasswordStrength password={passwordValue} />
          </div>
          <div className="form-group">
            <label htmlFor="user-role">{t('users:role')}</label>
            <select id="user-role" {...register('role')}>
              {ROLE_OPTIONS.map((value) => (
                <option key={value} value={value}>
                  {roleLabel(value)}
                </option>
              ))}
            </select>
          </div>
          <div className="form-group">
            <label htmlFor="user-active">{t('users:status')}</label>
            <select id="user-active" {...register('is_active')}>
              <option value="Y">{t('users:statusActive')}</option>
              <option value="N">{t('users:statusInactive')}</option>
            </select>
          </div>
        </Modal>
      )}

      {resetTarget && (
        <Modal
          title={t('users:resetTitle', { username: resetTarget.username })}
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
                {t('users:cancel')}
              </button>
              <button
                type="button"
                onClick={handleResetPassword}
                disabled={resetSubmitting || resetPassword.length < 8}
              >
                {resetSubmitting ? t('users:resetting') : t('users:confirmReset')}
              </button>
            </>
          }
        >
          {error && <div className="alert alert-error mb-3">{error}</div>}
          <div className="form-group">
            <label htmlFor="reset-password-input">{t('users:newPassword')}</label>
            <input
              id="reset-password-input"
              type="password"
              value={resetPassword}
              onChange={(e) => setResetPassword(e.target.value)}
              placeholder={t('users:passwordPlaceholder')}
            />
            <PasswordStrength password={resetPassword} />
          </div>
        </Modal>
      )}

      <ConfirmDialog
        open={!!deleteTarget}
        title={t('users:deleteTitle')}
        message={
          deleteTarget ? (
            <>
              {t('users:deleteMessage', { username: deleteTarget.username })}
              <br />
              <span style={{ color: 'var(--color-text-muted)', fontSize: '0.8125rem' }}>
                {t('users:deleteTip')}
              </span>
            </>
          ) : null
        }
        confirmText={t('users:confirmDelete')}
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
