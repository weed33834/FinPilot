import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import Modal from '../components/ui/Modal.tsx'
import ConfirmDialog from '../components/ui/ConfirmDialog.tsx'
import Loading from '../components/ui/Loading.tsx'
import EmptyState from '../components/ui/EmptyState.tsx'
import { ICONS } from '../components/ui/Icons.tsx'
import { toast } from '../components/ui/Toaster.tsx'
import { api } from '../api/client.ts'
import { getErrorMessage } from '../utils/errors.ts'
import { formatDateTime } from '../utils/format.ts'
import type { DataResponse, PaginatedResponse } from '../types/report.ts'
import type { ApiKey, ApiKeyWithPlain } from '../types/apiKey.ts'

export default function ApiKeysPage() {
  const { t } = useTranslation()
  const [keys, setKeys] = useState<ApiKey[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [form, setForm] = useState({ name: '', scopes: '', expires_at: '' })
  const [submitting, setSubmitting] = useState(false)
  // 创建 / 轮换后展示的一次性明文 key
  const [plainKey, setPlainKey] = useState<{ name: string; key: string } | null>(null)
  const [actingId, setActingId] = useState<string | null>(null)
  const [copiedId, setCopiedId] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<ApiKey | null>(null)
  const [revokeTarget, setRevokeTarget] = useState<ApiKey | null>(null)
  const [rotateTarget, setRotateTarget] = useState<ApiKey | null>(null)
  const [keyword, setKeyword] = useState('')

  const fetchKeys = async () => {
    setLoading(true)
    setError('')
    try {
      const response = await api.get<DataResponse<PaginatedResponse<ApiKey>>>('/api-keys', {
        params: { page: 1, page_size: 50 },
      })
      setKeys(response.data.data?.items || [])
    } catch (err) {
      setError(getErrorMessage(err, t('common:apiKeys.loadFailed')))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchKeys()
  }, [])

  // 关键词过滤（客户端，按名称/权限匹配）
  const filteredKeys = useMemo(() => {
    const kw = keyword.trim().toLowerCase()
    if (!kw) return keys
    return keys.filter(
      (k) =>
        (k.name || '').toLowerCase().includes(kw) ||
        k.scopes.some((s) => s.toLowerCase().includes(kw)),
    )
  }, [keys, keyword])

  const handleCreate = async () => {
    setSubmitting(true)
    setError('')
    try {
      const scopes = form.scopes
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
      const payload: Record<string, unknown> = { name: form.name, scopes }
      if (form.expires_at) {
        payload.expires_at = new Date(form.expires_at).toISOString()
      }
      const response = await api.post<DataResponse<ApiKeyWithPlain>>('/api-keys', payload)
      const created = response.data.data
      if (created) {
        setKeys((prev) => [created, ...prev])
        setPlainKey({ name: created.name, key: created.key })
        toast.success(t('common:apiKeys.toastCreated'))
      }
      setCreateOpen(false)
      setForm({ name: '', scopes: '', expires_at: '' })
    } catch (err) {
      setError(getErrorMessage(err, t('common:apiKeys.createFailed')))
    } finally {
      setSubmitting(false)
    }
  }

  const handleRotate = async (key: ApiKey) => {
    setActingId(key.id)
    setError('')
    try {
      const response = await api.post<DataResponse<ApiKeyWithPlain>>(
        `/api-keys/${key.id}/rotate`,
      )
      const rotated = response.data.data
      if (rotated) {
        // 旧 Key 置为禁用，新 Key 加入列表顶部
        setKeys((prev) => [
          rotated,
          ...prev.map((k) => (k.id === key.id ? { ...k, is_active: 'N' } : k)),
        ])
        setPlainKey({ name: rotated.name, key: rotated.key })
        toast.success(t('common:apiKeys.toastRotated'))
      }
    } catch (err) {
      toast.error(getErrorMessage(err, t('common:apiKeys.rotateFailed')))
    } finally {
      setActingId(null)
    }
  }

  const handleRevoke = async (key: ApiKey) => {
    setActingId(key.id)
    setError('')
    try {
      await api.post(`/api-keys/${key.id}/revoke`)
      setKeys((prev) =>
        prev.map((k) => (k.id === key.id ? { ...k, is_active: 'N' } : k)),
      )
      toast.success(t('common:apiKeys.toastRevoked'))
    } catch (err) {
      toast.error(getErrorMessage(err, t('common:apiKeys.revokeFailed')))
    } finally {
      setActingId(null)
    }
  }

  const handleDelete = async (key: ApiKey) => {
    setActingId(key.id)
    setError('')
    try {
      await api.delete(`/api-keys/${key.id}`)
      setKeys((prev) => prev.filter((k) => k.id !== key.id))
      toast.success(t('common:apiKeys.toastDeleted'))
    } catch (err) {
      toast.error(getErrorMessage(err, t('common:apiKeys.deleteFailed')))
    } finally {
      setActingId(null)
    }
  }

  const copyToClipboard = (text: string, id?: string) => {
    navigator.clipboard?.writeText(text).then(() => {
      setCopiedId(id || 'plain')
      setTimeout(() => setCopiedId(null), 2000)
    }).catch(() => {})
  }

  return (
    <div className="container">
      <div className="page-header">
        <h1>{t('common:apiKeys.title')}</h1>
        <button type="button" onClick={() => setCreateOpen(true)}>{t('common:apiKeys.create')}</button>
      </div>

      {error && (
        <div className="alert alert-error mb-4" role="alert">
          <span>{error}</span>
          <button type="button" className="chat-error-retry" onClick={fetchKeys}>
            {t('common:apiKeys.retry')}
          </button>
        </div>
      )}

      {keys.length > 0 && (
        <div className="toolbar">
          <div className="search-inline">
            <ICONS.search size={14} />
            <input
              type="search"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              placeholder={t('common:apiKeys.searchPlaceholder')}
              aria-label={t('common:apiKeys.searchPlaceholder')}
            />
          </div>
        </div>
      )}

      {loading ? (
        <Loading text={t('common:apiKeys.loading')} />
      ) : keys.length === 0 ? (
        <EmptyState
          icon="apiKeys"
          title={t('common:apiKeys.emptyTitle')}
          description={t('common:apiKeys.emptyDesc')}
          action={
            <button type="button" onClick={() => setCreateOpen(true)}>{t('common:apiKeys.create')}</button>
          }
        />
      ) : filteredKeys.length === 0 ? (
        <EmptyState
          icon="search"
          title={t('common:apiKeys.emptySearchTitle')}
          description={t('common:apiKeys.emptySearchDesc')}
        />
      ) : (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>{t('common:apiKeys.colName')}</th>
                <th>{t('common:apiKeys.colScopes')}</th>
                <th>{t('common:apiKeys.colStatus')}</th>
                <th>{t('common:apiKeys.colUsage')}</th>
                <th>{t('common:apiKeys.colLastUsed')}</th>
                <th>{t('common:apiKeys.colExpires')}</th>
                <th>{t('common:apiKeys.colActions')}</th>
              </tr>
            </thead>
            <tbody>
              {filteredKeys.map((key) => (
                <tr key={key.id}>
                  <td>{key.name}</td>
                  <td>
                    {key.scopes.length > 0 ? (
                      key.scopes.join(', ')
                    ) : (
                      <span className="text-muted">{t('common:apiKeys.allScopes')}</span>
                    )}
                  </td>
                  <td>
                    {key.is_active === 'Y' ? (
                      <span className="badge success">{t('common:apiKeys.statusActive')}</span>
                    ) : (
                      <span className="badge rejected">{t('common:apiKeys.statusRevoked')}</span>
                    )}
                  </td>
                  <td>{key.usage_count}</td>
                  <td>
                    {key.last_used_at ? (
                      formatDateTime(key.last_used_at)
                    ) : (
                      <span className="text-muted">—</span>
                    )}
                  </td>
                  <td>
                    {key.expires_at ? (
                      formatDateTime(key.expires_at)
                    ) : (
                      <span className="text-muted">{t('common:apiKeys.neverExpires')}</span>
                    )}
                  </td>
                  <td>
                    <div className="action-group">
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => setRotateTarget(key)}
                        disabled={actingId === key.id || key.is_active !== 'Y'}
                      >
                        {t('common:apiKeys.rotate')}
                      </button>
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => setRevokeTarget(key)}
                        disabled={actingId === key.id || key.is_active !== 'Y'}
                      >
                        {t('common:apiKeys.revoke')}
                      </button>
                      <button
                        type="button"
                        className="danger"
                        onClick={() => setDeleteTarget(key)}
                        disabled={actingId === key.id}
                      >
                        {t('common:apiKeys.delete')}
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
          title={t('common:apiKeys.createTitle')}
          onClose={() => setCreateOpen(false)}
          footer={
            <>
              <button type="button" className="secondary" onClick={() => setCreateOpen(false)}>
                {t('common:apiKeys.cancel')}
              </button>
              <button type="button" onClick={handleCreate} disabled={submitting || !form.name}>
                {submitting ? t('common:apiKeys.creating') : t('common:actions.create')}
              </button>
            </>
          }
        >
          {error && <div className="alert alert-error mb-3">{error}</div>}
          <div className="form-group">
            <label htmlFor="key-name">{t('common:apiKeys.name')}</label>
            <input
              id="key-name"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder={t('common:apiKeys.namePlaceholder')}
            />
          </div>
          <div className="form-group">
            <label htmlFor="key-scopes">{t('common:apiKeys.scopes')}</label>
            <input
              id="key-scopes"
              value={form.scopes}
              onChange={(e) => setForm({ ...form, scopes: e.target.value })}
              placeholder={t('common:apiKeys.scopesPlaceholder')}
            />
          </div>
          <div className="form-group">
            <label htmlFor="key-expires">{t('common:apiKeys.expires')}</label>
            <input
              id="key-expires"
              type="datetime-local"
              value={form.expires_at}
              onChange={(e) => setForm({ ...form, expires_at: e.target.value })}
            />
          </div>
        </Modal>
      )}

      {plainKey && (
        <Modal
          title={t('common:apiKeys.plainKeyTitle')}
          onClose={() => setPlainKey(null)}
          footer={
            <>
              <button type="button" className="secondary" onClick={() => copyToClipboard(plainKey.key)}>
                {copiedId === 'plain' ? t('common:apiKeys.copied') : t('common:apiKeys.copy')}
              </button>
              <button type="button" onClick={() => setPlainKey(null)}>{t('common:apiKeys.saved')}</button>
            </>
          }
        >
          <div className="alert alert-warning mb-4">
            {t('common:apiKeys.plainKeyWarning')}
          </div>
          <div className="code-block" style={{ wordBreak: 'break-all' }}>
            {plainKey.key}
          </div>
          <p className="text-muted text-sm mt-4">{t('common:apiKeys.plainKeyName', { name: plainKey.name })}</p>
        </Modal>
      )}

      <ConfirmDialog
        open={!!deleteTarget}
        title={t('common:apiKeys.confirmDeleteTitle')}
        message={deleteTarget ? <>{t('common:apiKeys.confirmDeleteMsg', { name: deleteTarget.name })}</> : null}
        confirmText={t('common:apiKeys.confirmDelete')}
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
        open={!!revokeTarget}
        title={t('common:apiKeys.confirmRevokeTitle')}
        message={revokeTarget ? <>{t('common:apiKeys.confirmRevokeMsg', { name: revokeTarget.name })}</> : null}
        confirmText={t('common:apiKeys.confirmRevoke')}
        variant="warning"
        onConfirm={async () => {
          if (revokeTarget) {
            await handleRevoke(revokeTarget)
            setRevokeTarget(null)
          }
        }}
        onCancel={() => setRevokeTarget(null)}
      />

      <ConfirmDialog
        open={!!rotateTarget}
        title={t('common:apiKeys.confirmRotateTitle')}
        message={rotateTarget ? <>{t('common:apiKeys.confirmRotateMsg', { name: rotateTarget.name })}</> : null}
        confirmText={t('common:apiKeys.confirmRotate')}
        variant="warning"
        onConfirm={async () => {
          if (rotateTarget) {
            await handleRotate(rotateTarget)
            setRotateTarget(null)
          }
        }}
        onCancel={() => setRotateTarget(null)}
      />
    </div>
  )
}
