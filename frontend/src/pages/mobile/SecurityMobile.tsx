import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import DOMPurify from 'dompurify'
import { api } from '../../api/client'
import { getErrorMessage } from '../../utils/errors'
import type { DataResponse } from '../../types/report'
import type { BackupCodesResponse, TwoFASetup, TwoFAStatus } from '../../types/twoFactor'
import { toast } from '../../components/ui/Toaster'
import MobilePageHeader from '../../components/mobile/MobilePageHeader'
import '../../i18n/mobile'

/**
 * 移动端安全中心：2FA 状态卡（启用/禁用/ regenerate 备份码）+ 修改密码卡。
 * 与桌面配置式表单一致的能力，但重排为单列触屏布局、增大点按区域。
 */
export default function SecurityMobile() {
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
    void fetchStatus()
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
      const resp = await api.post<DataResponse<BackupCodesResponse>>('/auth/2fa/backup-codes', {
        password: regenPassword,
      })
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

  return (
    <div className="msecurity">
      <MobilePageHeader title={t('security:title')} />

      {error && (
        <div className="msecurity__alert msecurity__alert--error" role="alert">
          {error}
        </div>
      )}
      {success && (
        <div className="msecurity__alert msecurity__alert--info" role="alert">
          {success}
        </div>
      )}

      {loading && !status ? (
        <div className="msecurity__loading">{t('loading')}</div>
      ) : (
        <>
          <section className="msecurity__card">
            <h3 className="msecurity__card-title">{t('twoFA.title')}</h3>

            {enabled ? (
              <div>
                <p className="msecurity__hint">
                  <span className="badge success">{t('twoFA.status.enabled')}</span>{' '}
                  <span>{t('twoFA.enabledHint')}</span>
                </p>

                {generatedCodes && (
                  <div className="msecurity__codes" role="alert">
                    <strong>{t('twoFA.backupCodes.savePrompt')}</strong>
                    <div className="msecurity__codes-grid">
                      {generatedCodes.map((code) => (
                        <code key={code}>{code}</code>
                      ))}
                    </div>
                    <button type="button" className="msecurity__link" onClick={() => void copyAllCodes()}>
                      {t('twoFA.backupCodes.copyAll')}
                    </button>
                    <p className="msecurity__hint">{t('twoFA.backupCodes.usageHint')}</p>
                  </div>
                )}

                <div className="msecurity__field-group">
                  <label htmlFor="regen-pw">{t('fields.currentPassword.label')}</label>
                  <input
                    id="regen-pw"
                    type="password"
                    placeholder={t('fields.currentPassword.placeholder')}
                    value={regenPassword}
                    onChange={(e) => setRegenPassword(e.target.value)}
                    autoComplete="current-password"
                  />
                  <button type="button" onClick={() => void handleRegenerate()} disabled={loading}>
                    {loading ? t('actions.regenerating') : t('actions.regenerate')}
                  </button>
                </div>

                <div className="msecurity__field-group">
                  <label htmlFor="disable-pw">{t('fields.currentPassword.label')}</label>
                  <input
                    id="disable-pw"
                    type="password"
                    placeholder={t('fields.currentPassword.placeholder')}
                    value={disablePassword}
                    onChange={(e) => setDisablePassword(e.target.value)}
                    autoComplete="current-password"
                  />
                  <button type="button" onClick={() => void handleDisable()} disabled={loading} className="danger">
                    {loading ? t('actions.disabling') : t('twoFA.disable.title')}
                  </button>
                </div>
              </div>
            ) : setupData ? (
              <div>
                <p className="msecurity__hint">{t('twoFA.setup.step1')}</p>
                <div
                  className="msecurity__qr"
                  dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(setupData.qr_svg) }}
                />
                <p className="msecurity__hint">
                  {t('twoFA.setup.manualSecret')}
                  <code>{setupData.secret}</code>
                </p>
                <form onSubmit={handleEnable}>
                  <div className="msecurity__field-group">
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
                  <div className="msecurity__field-group">
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
                  <div className="msecurity__row">
                    <button type="submit" disabled={loading}>
                      {loading ? t('actions.enabling') : t('actions.confirmEnable')}
                    </button>
                    <button type="button" className="secondary" onClick={() => setSetupData(null)}>
                      {t('actions.cancel')}
                    </button>
                  </div>
                </form>
              </div>
            ) : (
              <div>
                <p className="msecurity__hint">
                  <span className="badge draft">
                    {setupInProgress ? t('twoFA.status.setupInProgress') : t('twoFA.status.disabled')}
                  </span>{' '}
                  <span>{t('twoFA.disabledHint')}</span>
                </p>
                <button type="button" onClick={() => void handleSetup()} disabled={loading}>
                  {setupInProgress ? t('actions.regenerateSecret') : t('actions.enable')}
                </button>
              </div>
            )}
          </section>

          <section className="msecurity__card">
            <h3 className="msecurity__card-title">{t('changePassword.title')}</h3>
            <p className="msecurity__hint">{t('changePassword.hint')}</p>
            <form onSubmit={handleChangePassword}>
              <div className="msecurity__field-group">
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
              <div className="msecurity__field-group">
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
              <div className="msecurity__field-group">
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
          </section>
        </>
      )}
    </div>
  )
}
