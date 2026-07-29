import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import DOMPurify from 'dompurify'
import Loading from '../components/ui/Loading.tsx'
import ConfirmDialog from '../components/ui/ConfirmDialog.tsx'
import { toast } from '../components/ui/Toaster.tsx'
import { api } from '../api/client.ts'
import { getErrorMessage } from '../utils/errors.ts'
import type { DataResponse } from '../types/report.ts'
import type { BackupCodesResponse, TwoFASetup, TwoFAStatus } from '../types/twoFactor.ts'

export default function SecurityPage() {
  const { t } = useTranslation('security')
  const [status, setStatus] = useState<TwoFAStatus | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const [setupData, setSetupData] = useState<TwoFASetup | null>(null)
  const [enableCode, setEnableCode] = useState('')
  const [enablePassword, setEnablePassword] = useState('')
  const [generatedCodes, setGeneratedCodes] = useState<string[] | null>(null)

  const [disablePassword, setDisablePassword] = useState('')
  const [disableConfirmOpen, setDisableConfirmOpen] = useState(false)
  const [regenPassword, setRegenPassword] = useState('')

  const [changePwCurrent, setChangePwCurrent] = useState('')
  const [changePwNew, setChangePwNew] = useState('')
  const [changePwConfirm, setChangePwConfirm] = useState('')

  const fetchStatus = async () => {
    setLoading(true)
    setError('')
    try {
      const resp = await api.get<DataResponse<TwoFAStatus>>('/auth/2fa/status')
      setStatus(resp.data.data)
    } catch (err) {
      setError(getErrorMessage(err, t('errors.fetchStatusFailed')))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchStatus()
  }, [])

  const clearMessages = () => {
    setError('')
    setSuccess('')
  }

  const handleSetup = async () => {
    clearMessages()
    setLoading(true)
    try {
      const resp = await api.post<DataResponse<TwoFASetup>>('/auth/2fa/setup')
      setSetupData(resp.data.data)
    } catch (err) {
      setError(getErrorMessage(err, t('errors.setupFailed')))
    } finally {
      setLoading(false)
    }
  }

  const handleEnable = async (e: React.FormEvent) => {
    e.preventDefault()
    clearMessages()
    if (!enableCode) {
      toast.warning(t('validation.codeRequired'))
      return
    }
    if (!enablePassword) {
      toast.warning(t('validation.passwordRequired'))
      return
    }
    setLoading(true)
    try {
      const resp = await api.post<DataResponse<BackupCodesResponse>>('/auth/2fa/enable', {
        totp_code: enableCode,
        password: enablePassword,
      })
      setGeneratedCodes(resp.data.data.backup_codes)
      setSetupData(null)
      setEnableCode('')
      setEnablePassword('')
      setSuccess(t('toast.enabled.title'))
      toast.success(t('toast.enabled.title'), t('toast.enabled.description'))
      await fetchStatus()
    } catch (err) {
      setError(getErrorMessage(err, t('errors.enableFailed')))
    } finally {
      setLoading(false)
    }
  }

  const handleDisable = async () => {
    clearMessages()
    if (!disablePassword) {
      toast.warning(t('validation.passwordRequired'))
      return
    }
    setDisableConfirmOpen(true)
  }

  const confirmDisable = async () => {
    setDisableConfirmOpen(false)
    setLoading(true)
    try {
      await api.post('/auth/2fa/disable', { password: disablePassword })
      setDisablePassword('')
      setGeneratedCodes(null)
      setSuccess(t('toast.disabled.title'))
      toast.success(t('toast.disabled.title'), t('toast.disabled.description'))
      await fetchStatus()
    } catch (err) {
      const msg = getErrorMessage(err, t('errors.disableFailed'))
      setError(msg)
      toast.error(msg)
    } finally {
      setLoading(false)
    }
  }

  const handleRegenerate = async () => {
    clearMessages()
    if (!regenPassword) {
      toast.warning(t('validation.passwordRequired'))
      return
    }
    setLoading(true)
    try {
      const resp = await api.post<DataResponse<BackupCodesResponse>>(
        '/auth/2fa/backup-codes',
        { password: regenPassword },
      )
      setGeneratedCodes(resp.data.data.backup_codes)
      setRegenPassword('')
      setSuccess(t('toast.regenerated.title'))
      toast.success(t('toast.regenerated.title'), t('toast.regenerated.description'))
    } catch (err) {
      setError(getErrorMessage(err, t('errors.regenerateFailed')))
    } finally {
      setLoading(false)
    }
  }

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault()
    clearMessages()
    if (changePwNew !== changePwConfirm) {
      toast.warning(t('validation.passwordMismatch'))
      return
    }
    setLoading(true)
    try {
      await api.post('/auth/change-password', {
        current_password: changePwCurrent,
        new_password: changePwNew,
      })
      setChangePwCurrent('')
      setChangePwNew('')
      setChangePwConfirm('')
      setSuccess(t('toast.passwordChanged.title'))
      toast.success(t('toast.passwordChanged.title'))
    } catch (err) {
      setError(getErrorMessage(err, t('errors.changePasswordFailed')))
    } finally {
      setLoading(false)
    }
  }

  const copyAllCodes = async () => {
    if (!generatedCodes) return
    try {
      await navigator.clipboard.writeText(generatedCodes.join('\n'))
      setSuccess(t('toast.codesCopied.title'))
      toast.success(t('toast.codesCopied.title'))
    } catch {
      setError(t('errors.copyFailed'))
    }
  }

  const enabled = status?.enabled ?? false
  const setupInProgress = status?.setup_in_progress ?? false

  // 加载失败且无状态时显示重试
  if (!loading && !status && error) {
    return (
      <div className="container">
        <div className="page-header">
          <h1>{t('title')}</h1>
        </div>
        <div className="empty-state">
          <p className="text-muted text-sm">{t('loadFailed')}</p>
          <button type="button" className="secondary mt-2" onClick={fetchStatus}>
            {t('actions.retry')}
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="container">
      <div className="page-header">
        <h1>{t('title')}</h1>
      </div>

      {error && (
        <div className="alert alert-error mb-4" role="alert">
          {error}
        </div>
      )}
      {success && (
        <div className="alert alert-info mb-4" role="alert">
          {success}
        </div>
      )}

      {loading && !status ? (
        <Loading text={t('loading')} />
      ) : (
        <>
          <div className="card mb-4">
            <h3 className="card-title">{t('twoFA.title')}</h3>

            {enabled ? (
              <div>
                <p className="text-sm">
                  <span className="badge success">{t('twoFA.status.enabled')}</span>
                  <span className="ml-2">{t('twoFA.enabledHint')}</span>
                </p>

                {generatedCodes && (
                  <div className="alert alert-warning mt-4" role="alert">
                    <strong>{t('twoFA.backupCodes.savePrompt')}</strong>
                    <div className="backup-codes-grid mt-2">
                      {generatedCodes.map((code) => (
                        <code key={code}>{code}</code>
                      ))}
                    </div>
                    <div className="mt-2">
                      <button type="button" className="link" onClick={copyAllCodes}>
                        {t('twoFA.backupCodes.copyAll')}
                      </button>
                    </div>
                    <p className="text-sm mt-2">{t('twoFA.backupCodes.usageHint')}</p>
                  </div>
                )}

                <div className="mt-4">
                  <h4>{t('twoFA.regenerate.title')}</h4>
                  <p className="text-sm text-muted">{t('twoFA.regenerate.hint')}</p>
                  <div className="form-group">
                    <label htmlFor="regen-pw">{t('fields.currentPassword.label')}</label>
                    <input
                      id="regen-pw"
                      type="password"
                      placeholder={t('fields.currentPassword.placeholder')}
                      value={regenPassword}
                      onChange={(e) => setRegenPassword(e.target.value)}
                      autoComplete="current-password"
                    />
                  </div>
                  <button type="button" onClick={handleRegenerate} disabled={loading}>
                    {loading ? t('actions.regenerating') : t('actions.regenerate')}
                  </button>
                </div>

                <div className="mt-4">
                  <h4>{t('twoFA.disable.title')}</h4>
                  <p className="text-sm text-muted">{t('twoFA.disable.hint')}</p>
                  <div className="form-group">
                    <label htmlFor="disable-pw">{t('fields.currentPassword.label')}</label>
                    <input
                      id="disable-pw"
                      type="password"
                      placeholder={t('fields.currentPassword.placeholder')}
                      value={disablePassword}
                      onChange={(e) => setDisablePassword(e.target.value)}
                      autoComplete="current-password"
                    />
                  </div>
                  <button type="button" onClick={handleDisable} disabled={loading} className="danger">
                    {loading ? t('actions.disabling') : t('twoFA.disable.title')}
                  </button>
                </div>
              </div>
            ) : setupData ? (
              <div>
                <p className="text-sm">{t('twoFA.setup.step1')}</p>
                <div
                  className="qr-display"
                  dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(setupData.qr_svg) }}
                />
                <p className="text-sm text-muted mt-2">
                  {t('twoFA.setup.manualSecret')}<code>{setupData.secret}</code>
                </p>
                <form onSubmit={handleEnable} className="mt-4">
                  <div className="form-group">
                    <label htmlFor="enable-code">{t('twoFA.setup.step2')}</label>
                    <input
                      id="enable-code"
                      value={enableCode}
                      onChange={(e) => setEnableCode(e.target.value)}
                      placeholder={t('fields.code.placeholder')}
                      inputMode="numeric"
                      maxLength={8}
                      autoComplete="one-time-code"
                      required
                    />
                  </div>
                  <div className="form-group">
                    <label htmlFor="enable-pw">{t('fields.currentPassword.label')}</label>
                    <input
                      id="enable-pw"
                      type="password"
                      placeholder={t('fields.currentPassword.placeholder')}
                      value={enablePassword}
                      onChange={(e) => setEnablePassword(e.target.value)}
                      autoComplete="current-password"
                      required
                    />
                  </div>
                  <div className="form-row">
                    <button type="submit" disabled={loading}>
                      {loading ? t('actions.enabling') : t('actions.confirmEnable')}
                    </button>
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => setSetupData(null)}
                    >
                      {t('actions.cancel')}
                    </button>
                  </div>
                </form>
              </div>
            ) : (
              <div>
                <p className="text-sm">
                  <span className="badge draft">
                    {setupInProgress ? t('twoFA.status.setupInProgress') : t('twoFA.status.disabled')}
                  </span>
                  <span className="ml-2">{t('twoFA.disabledHint')}</span>
                </p>
                <button type="button" onClick={handleSetup} disabled={loading} className="mt-2">
                  {setupInProgress ? t('actions.regenerateSecret') : t('actions.enable')}
                </button>
              </div>
            )}
          </div>

          <div className="card">
            <h3 className="card-title">{t('changePassword.title')}</h3>
            <p className="text-sm text-muted mb-4">{t('changePassword.hint')}</p>
            <form onSubmit={handleChangePassword}>
              <div className="form-group">
                <label htmlFor="current-pw">{t('fields.currentPassword.label')}</label>
                <input
                  id="current-pw"
                  type="password"
                  value={changePwCurrent}
                  onChange={(e) => setChangePwCurrent(e.target.value)}
                  autoComplete="current-password"
                  required
                />
              </div>
              <div className="form-group">
                <label htmlFor="new-pw">{t('fields.newPassword.label')}</label>
                <input
                  id="new-pw"
                  type="password"
                  value={changePwNew}
                  onChange={(e) => setChangePwNew(e.target.value)}
                  autoComplete="new-password"
                  required
                />
              </div>
              <div className="form-group">
                <label htmlFor="confirm-pw">{t('fields.confirmPassword.label')}</label>
                <input
                  id="confirm-pw"
                  type="password"
                  value={changePwConfirm}
                  onChange={(e) => setChangePwConfirm(e.target.value)}
                  autoComplete="new-password"
                  required
                />
              </div>
              <button type="submit" disabled={loading}>
                {loading ? t('actions.changing') : t('changePassword.title')}
              </button>
            </form>
          </div>
        </>
      )}

      <ConfirmDialog
        open={disableConfirmOpen}
        title={t('twoFA.disable.confirmTitle')}
        message={
          <>
            {t('twoFA.disable.confirmMessage')}
            <br />
            <span style={{ color: 'var(--color-text-muted)', fontSize: '0.8125rem' }}>
              {t('twoFA.disable.confirmHint')}
            </span>
          </>
        }
        confirmText={t('actions.confirmDisable')}
        variant="warning"
        onConfirm={confirmDisable}
        onCancel={() => setDisableConfirmOpen(false)}
      />
    </div>
  )
}
