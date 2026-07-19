import { useEffect, useState } from 'react'
import DOMPurify from 'dompurify'
import Loading from '../components/ui/Loading.tsx'
import ConfirmDialog from '../components/ui/ConfirmDialog.tsx'
import { toast } from '../components/ui/Toaster.tsx'
import { api } from '../api/client.ts'
import { getErrorMessage } from '../utils/errors.ts'
import type { DataResponse } from '../types/report.ts'
import type { BackupCodesResponse, TwoFASetup, TwoFAStatus } from '../types/twoFactor.ts'

export default function SecurityPage() {
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
      setError(getErrorMessage(err, '获取 2FA 状态失败'))
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
      setError(getErrorMessage(err, '生成 2FA 密钥失败'))
    } finally {
      setLoading(false)
    }
  }

  const handleEnable = async (e: React.FormEvent) => {
    e.preventDefault()
    clearMessages()
    if (!enableCode) {
      setError('请输入验证码')
      return
    }
    if (!enablePassword) {
      setError('请输入当前密码')
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
      setSuccess('2FA 已启用，请妥善保存备份码')
      await fetchStatus()
    } catch (err) {
      setError(getErrorMessage(err, '启用 2FA 失败'))
    } finally {
      setLoading(false)
    }
  }

  const handleDisable = async () => {
    clearMessages()
    if (!disablePassword) {
      setError('请输入当前密码')
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
      setSuccess('2FA 已关闭')
      toast.success('2FA 已关闭', '登录安全性已降低，建议尽快重新启用。')
      await fetchStatus()
    } catch (err) {
      const msg = getErrorMessage(err, '关闭 2FA 失败')
      setError(msg)
      toast.error(msg)
    } finally {
      setLoading(false)
    }
  }

  const handleRegenerate = async () => {
    clearMessages()
    if (!regenPassword) {
      setError('请输入当前密码')
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
      setSuccess('备份码已重新生成，旧码已失效')
    } catch (err) {
      setError(getErrorMessage(err, '重新生成备份码失败'))
    } finally {
      setLoading(false)
    }
  }

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault()
    clearMessages()
    if (changePwNew !== changePwConfirm) {
      setError('两次输入的新密码不一致')
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
      setSuccess('密码修改成功')
    } catch (err) {
      setError(getErrorMessage(err, '密码修改失败'))
    } finally {
      setLoading(false)
    }
  }

  const copyAllCodes = async () => {
    if (!generatedCodes) return
    try {
      await navigator.clipboard.writeText(generatedCodes.join('\n'))
      setSuccess('备份码已复制到剪贴板')
    } catch {
      setError('复制失败，请手动保存')
    }
  }

  const enabled = status?.enabled ?? false
  const setupInProgress = status?.setup_in_progress ?? false

  // 加载失败且无状态时显示重试
  if (!loading && !status && error) {
    return (
      <div className="container">
        <div className="page-header">
          <h1>安全设置</h1>
        </div>
        <div className="empty-state">
          <p className="text-muted text-sm">加载失败</p>
          <button type="button" className="secondary mt-2" onClick={fetchStatus}>重试</button>
        </div>
      </div>
    )
  }

  return (
    <div className="container">
      <div className="page-header">
        <h1>安全设置</h1>
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
        <Loading text="加载安全设置中..." />
      ) : (
        <>
          <div className="card mb-4">
            <h3 className="card-title">双因素认证（2FA）</h3>

            {enabled ? (
              <div>
                <p className="text-sm">
                  <span className="badge success">已启用</span>
                  <span className="ml-2">登录时需输入验证码</span>
                </p>

                {generatedCodes && (
                  <div className="alert alert-warning mt-4" role="alert">
                    <strong>请立即保存以下备份码（关闭页面后无法再次查看）：</strong>
                    <div className="backup-codes-grid mt-2">
                      {generatedCodes.map((code) => (
                        <code key={code}>{code}</code>
                      ))}
                    </div>
                    <div className="mt-2">
                      <button type="button" className="link" onClick={copyAllCodes}>
                        复制全部
                      </button>
                    </div>
                    <p className="text-sm mt-2">
                      每个备份码仅可用一次，请离线保存（密码管理器或打印）。
                    </p>
                  </div>
                )}

                <div className="mt-4">
                  <h4>重新生成备份码</h4>
                  <p className="text-sm text-muted">生成新备份码后，旧备份码立即失效。</p>
                  <div className="form-group">
                    <label htmlFor="regen-pw">当前密码</label>
                    <input
                      id="regen-pw"
                      type="password"
                      placeholder="当前密码"
                      value={regenPassword}
                      onChange={(e) => setRegenPassword(e.target.value)}
                      autoComplete="current-password"
                    />
                  </div>
                  <button type="button" onClick={handleRegenerate} disabled={loading}>
                    {loading ? '重新生成中...' : '重新生成'}
                  </button>
                </div>

                <div className="mt-4">
                  <h4>关闭 2FA</h4>
                  <p className="text-sm text-muted">关闭后登录仅需密码，安全性降低。</p>
                  <div className="form-group">
                    <label htmlFor="disable-pw">当前密码</label>
                    <input
                      id="disable-pw"
                      type="password"
                      placeholder="当前密码"
                      value={disablePassword}
                      onChange={(e) => setDisablePassword(e.target.value)}
                      autoComplete="current-password"
                    />
                  </div>
                  <button type="button" onClick={handleDisable} disabled={loading} className="danger">
                    {loading ? '关闭中...' : '关闭 2FA'}
                  </button>
                </div>
              </div>
            ) : setupData ? (
              <div>
                <p className="text-sm">
                  1. 用 Authenticator App 扫描下方二维码，或手动输入密钥。
                </p>
                <div
                  className="qr-display"
                  dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(setupData.qr_svg) }}
                />
                <p className="text-sm text-muted mt-2">
                  手动输入密钥：<code>{setupData.secret}</code>
                </p>
                <form onSubmit={handleEnable} className="mt-4">
                  <div className="form-group">
                    <label htmlFor="enable-code">2. 输入 App 显示的 6 位验证码</label>
                    <input
                      id="enable-code"
                      value={enableCode}
                      onChange={(e) => setEnableCode(e.target.value)}
                      placeholder="6 位验证码"
                      inputMode="numeric"
                      maxLength={8}
                      autoComplete="one-time-code"
                      required
                    />
                  </div>
                  <div className="form-group">
                    <label htmlFor="enable-pw">当前密码</label>
                    <input
                      id="enable-pw"
                      type="password"
                      placeholder="当前密码"
                      value={enablePassword}
                      onChange={(e) => setEnablePassword(e.target.value)}
                      autoComplete="current-password"
                      required
                    />
                  </div>
                  <div className="form-row">
                    <button type="submit" disabled={loading}>
                      {loading ? '启用中...' : '确认启用'}
                    </button>
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => setSetupData(null)}
                    >
                      取消
                    </button>
                  </div>
                </form>
              </div>
            ) : (
              <div>
                <p className="text-sm">
                  <span className="badge draft">
                    {setupInProgress ? '设置中' : '未启用'}
                  </span>
                  <span className="ml-2">启用后登录需额外输入验证码</span>
                </p>
                <button type="button" onClick={handleSetup} disabled={loading} className="mt-2">
                  {setupInProgress ? '重新生成密钥' : '启用 2FA'}
                </button>
              </div>
            )}
          </div>

          <div className="card">
            <h3 className="card-title">修改密码</h3>
            <p className="text-sm text-muted mb-4">密码至少 8 位，需含大小写字母与数字。</p>
            <form onSubmit={handleChangePassword}>
              <div className="form-group">
                <label htmlFor="current-pw">当前密码</label>
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
                <label htmlFor="new-pw">新密码</label>
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
                <label htmlFor="confirm-pw">确认新密码</label>
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
                {loading ? '修改中...' : '修改密码'}
              </button>
            </form>
          </div>
        </>
      )}

      <ConfirmDialog
        open={disableConfirmOpen}
        title="确认关闭 2FA"
        message={
          <>
            关闭后登录仅需密码，安全性将降低。
            <br />
            <span style={{ color: 'var(--color-text-muted)', fontSize: '0.8125rem' }}>
              建议尽快重新启用以保护账户安全。
            </span>
          </>
        }
        confirmText="确认关闭"
        variant="warning"
        onConfirm={confirmDisable}
        onCancel={() => setDisableConfirmOpen(false)}
      />
    </div>
  )
}
