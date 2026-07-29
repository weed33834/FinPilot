import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { useAuth } from '../context/AuthContext.tsx'
import { getErrorMessage } from '../utils/errors.ts'

const loginSchema = z.object({
  username: z.string().min(1, '请输入用户名'),
  password: z.string().min(1, '请输入密码'),
  rememberMe: z.boolean(),
})

type LoginForm = z.infer<typeof loginSchema>

type Step = 'credentials' | 'twofa'

export default function LoginPage() {
  const { t } = useTranslation(['auth', 'brand', 'footer'])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const { login, verify2fa } = useAuth()
  const navigate = useNavigate()

  // 2FA 步骤状态
  const [step, setStep] = useState<Step>('credentials')
  const [challengeToken, setChallengeToken] = useState('')
  const [rememberMe, setRememberMe] = useState(false)
  const [useBackup, setUseBackup] = useState(false)
  const [totpCode, setTotpCode] = useState('')
  const [backupCode, setBackupCode] = useState('')

  const {
    register,
    handleSubmit,
    formState: { errors, isValid },
  } = useForm<LoginForm>({
    resolver: zodResolver(loginSchema),
    defaultValues: { username: '', password: '', rememberMe: false },
    mode: 'onChange',
  })

  const onSubmit = async (data: LoginForm) => {
    setError('')
    setLoading(true)
    try {
      const result = await login(data.username, data.password, data.rememberMe)
      if (result.requires2fa) {
        // 进入 2FA 验证步骤；若无 challengeToken（Redis 不可用降级），提示联系管理员
        if (!result.challengeToken) {
          setError(t('login.requires2faHint'))
          return
        }
        setChallengeToken(result.challengeToken)
        setRememberMe(data.rememberMe)
        setStep('twofa')
        return
      }
      navigate('/dashboard')
    } catch (err) {
      setError(getErrorMessage(err, t('login.failed')))
    } finally {
      setLoading(false)
    }
  }

  const onVerify2fa = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    const code = useBackup ? backupCode.trim() : totpCode.trim()
    if (!code) {
      setError(useBackup ? t('login.enterBackupCode') : t('login.enterCode'))
      return
    }
    setLoading(true)
    try {
      await verify2fa(
        challengeToken,
        useBackup ? undefined : totpCode,
        useBackup ? backupCode : undefined,
      )
      navigate('/dashboard')
    } catch (err) {
      setError(getErrorMessage(err, t('login.verifyFailed')))
    } finally {
      setLoading(false)
    }
  }

  const backToCredentials = () => {
    setError('')
    setTotpCode('')
    setBackupCode('')
    setUseBackup(false)
    setStep('credentials')
  }

  // 记住我勾选同步给 2FA 步骤（login 时已传，此处仅用于 UI 一致）
  void rememberMe

  return (
    <div className="login-page">
      {/* 左侧品牌展示区 - 桌面端显示 */}
      <aside className="login-brand-panel" aria-hidden="true">
        <div className="login-brand-content">
          <div className="login-brand-mark">
            <div className="login-brand-logo">FP</div>
            <div>
              <div className="login-brand-name">FinPilot</div>
              <div className="login-brand-tagline">{t('brand:tagline')}</div>
            </div>
          </div>
          <h2 className="login-brand-headline">{t('brand:headline')}</h2>
          <ul className="login-brand-features">
            <li>
              <span className="login-brand-bullet" />
              <div>
                <strong>{t('brand:featureSmartQueryTitle')}</strong>
                <span>{t('brand:featureSmartQueryDesc')}</span>
              </div>
            </li>
            <li>
              <span className="login-brand-bullet" />
              <div>
                <strong>{t('brand:featureMultiAnalysisTitle')}</strong>
                <span>{t('brand:featureMultiAnalysisDesc')}</span>
              </div>
            </li>
            <li>
              <span className="login-brand-bullet" />
              <div>
                <strong>{t('brand:featureComplianceTitle')}</strong>
                <span>{t('brand:featureComplianceDesc')}</span>
              </div>
            </li>
          </ul>
        </div>
      </aside>

      {/* 右侧登录表单 */}
      <main className="login-form-panel">
        <div className="login-card">
          {step === 'credentials' && (
            <>
              <div className="login-card-header">
                <h1>{t('login.title')}</h1>
                <p className="login-subtitle">{t('login.subtitle')}</p>
              </div>

              <form onSubmit={handleSubmit(onSubmit)} className="login-form" noValidate>
                <div className="form-group">
                  <label htmlFor="username">{t('login.username')}</label>
                  <div className={`login-input-wrap ${errors.username ? 'has-error' : ''}`}>
                    <span className="login-input-icon" aria-hidden="true">
                      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8">
                        <circle cx="12" cy="8" r="4" />
                        <path d="M4 21c0-4.4 3.6-8 8-8s8 3.6 8 8" />
                      </svg>
                    </span>
                    <input
                      id="username"
                      {...register('username')}
                      autoComplete="username"
                      autoFocus
                      placeholder={t('auth:login.usernamePlaceholder')}
                      aria-invalid={errors.username ? 'true' : 'false'}
                    />
                  </div>
                  {errors.username && (
                    <span className="form-error" role="alert">
                      {errors.username.message}
                    </span>
                  )}
                </div>

                <div className="form-group">
                  <label htmlFor="password">{t('login.password')}</label>
                  <div className={`login-input-wrap ${errors.password ? 'has-error' : ''}`}>
                    <span className="login-input-icon" aria-hidden="true">
                      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8">
                        <rect x="4" y="11" width="16" height="10" rx="2" />
                        <path d="M8 11V7a4 4 0 1 1 8 0v4" />
                      </svg>
                    </span>
                    <input
                      id="password"
                      type={showPassword ? 'text' : 'password'}
                      {...register('password')}
                      autoComplete="current-password"
                      placeholder={t('auth:login.passwordPlaceholder')}
                      aria-invalid={errors.password ? 'true' : 'false'}
                    />
                    <button
                      type="button"
                      className="login-toggle-pwd"
                      onClick={() => setShowPassword((s) => !s)}
                      aria-label={showPassword ? t('auth:login.hidePassword') : t('auth:login.showPassword')}
                      tabIndex={-1}
                    >
                      {showPassword ? (
                        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8">
                          <path d="M3 3l18 18M10.6 10.6a2 2 0 0 0 2.8 2.8M9.9 5.1A10 10 0 0 1 12 5c5 0 9 4 10 7a13 13 0 0 1-3.4 4.5M6.5 7.2C4 9 3 11 2 12c1 3 5 7 10 7 1.7 0 3.2-.4 4.6-1" />
                        </svg>
                      ) : (
                        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8">
                          <path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7z" />
                          <circle cx="12" cy="12" r="3" />
                        </svg>
                      )}
                    </button>
                  </div>
                  {errors.password && (
                    <span className="form-error" role="alert">
                      {errors.password.message}
                    </span>
                  )}
                </div>

                <div className="login-form-row">
                  <label className="remember-me" htmlFor="remember-me">
                    <input id="remember-me" type="checkbox" {...register('rememberMe')} />
                    <span>{t('login.rememberMe')}</span>
                  </label>
                  <a href="#forgot" className="login-forgot-link" onClick={(e) => e.preventDefault()}>
                    {t('auth:login.forgotPassword')}
                  </a>
                </div>

                {error && (
                  <div className="alert alert-error" role="alert">
                    <span className="alert-icon" aria-hidden="true">!</span>
                    <span>{error}</span>
                  </div>
                )}

                <button
                  type="submit"
                  disabled={loading || !isValid}
                  className="login-submit"
                >
                  {loading ? (
                    <>
                      <span className="login-spinner" aria-hidden="true" />
                      <span>{t('login.submitting')}</span>
                    </>
                  ) : (
                    t('login.submit')
                  )}
                </button>
              </form>
            </>
          )}

          {step === 'twofa' && (
            <>
              <div className="login-card-header">
                <h1>{t('login.twofaTitle')}</h1>
                <p className="login-subtitle">
                  {useBackup ? t('login.backupSubtitle') : t('login.totpSubtitle')}
                </p>
              </div>

              <form onSubmit={onVerify2fa} className="login-form" noValidate>
                {!useBackup ? (
                  <div className="form-group">
                    <label htmlFor="totp-code">{t('login.totpCode')}</label>
                    <div className="login-input-wrap">
                      <span className="login-input-icon" aria-hidden="true">
                        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8">
                          <rect x="4" y="5" width="16" height="16" rx="2" />
                          <path d="M8 3v4M16 3v4M4 10h16" />
                        </svg>
                      </span>
                      <input
                        id="totp-code"
                        value={totpCode}
                        onChange={(e) => setTotpCode(e.target.value)}
                        autoComplete="one-time-code"
                        autoFocus
                        inputMode="numeric"
                        maxLength={8}
                        placeholder={t('login.totpPlaceholder')}
                      />
                    </div>
                  </div>
                ) : (
                  <div className="form-group">
                    <label htmlFor="backup-code">{t('login.backupCode')}</label>
                    <div className="login-input-wrap">
                      <span className="login-input-icon" aria-hidden="true">
                        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8">
                          <path d="M12 2l9 4v6c0 5-3.8 9-9 10-5.2-1-9-5-9-10V6l9-4z" />
                        </svg>
                      </span>
                      <input
                        id="backup-code"
                        value={backupCode}
                        onChange={(e) => setBackupCode(e.target.value)}
                        autoComplete="off"
                        autoFocus
                        placeholder={t('login.backupPlaceholder')}
                      />
                    </div>
                  </div>
                )}

                {error && (
                  <div className="alert alert-error" role="alert">
                    <span className="alert-icon" aria-hidden="true">!</span>
                    <span>{error}</span>
                  </div>
                )}

                <button type="submit" disabled={loading} className="login-submit">
                  {loading ? (
                    <>
                      <span className="login-spinner" aria-hidden="true" />
                      <span>{t('login.verifying')}</span>
                    </>
                  ) : (
                    t('login.verify')
                  )}
                </button>

                <div className="login-form-row login-twofa-switch">
                  <button
                    type="button"
                    className="link"
                    onClick={() => {
                      setError('')
                      setUseBackup((v) => !v)
                    }}
                  >
                    {useBackup ? t('login.useTotp') : t('login.useBackup')}
                  </button>
                  <button type="button" className="link" onClick={backToCredentials}>
                    {t('login.backToLogin')}
                  </button>
                </div>
              </form>
            </>
          )}

          <footer className="login-card-footer">
            <span>{t('footer:agreeTerms')}</span>
            <a href="#terms" onClick={(e) => e.preventDefault()}>{t('footer:terms')}</a>
            <span>{t('footer:and')}</span>
            <a href="#privacy" onClick={(e) => e.preventDefault()}>{t('footer:privacy')}</a>
          </footer>
        </div>
      </main>
    </div>
  )
}
