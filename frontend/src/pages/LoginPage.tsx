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

export default function LoginPage() {
  const { t } = useTranslation('auth')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const { login } = useAuth()
  const navigate = useNavigate()

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
        setError(t('login.requires2faHint'))
        return
      }
      navigate('/dashboard')
    } catch (err) {
      setError(getErrorMessage(err, t('login.failed')))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-page">
      {/* 左侧品牌展示区 - 桌面端显示 */}
      <aside className="login-brand-panel" aria-hidden="true">
        <div className="login-brand-content">
          <div className="login-brand-mark">
            <div className="login-brand-logo">FP</div>
            <div>
              <div className="login-brand-name">FinPilot</div>
              <div className="login-brand-tagline">FINANCIAL ANALYSIS</div>
            </div>
          </div>
          <h2 className="login-brand-headline">企业级财务智能分析平台</h2>
          <ul className="login-brand-features">
            <li>
              <span className="login-brand-bullet" />
              <div>
                <strong>智能查询</strong>
                <span>自然语言转 SQL，秒级响应</span>
              </div>
            </li>
            <li>
              <span className="login-brand-bullet" />
              <div>
                <strong>多维分析</strong>
                <span>KPI 看板、趋势对比、钻取洞察</span>
              </div>
            </li>
            <li>
              <span className="login-brand-bullet" />
              <div>
                <strong>合规安全</strong>
                <span>审计日志、ABAC 策略、API 密钥管控</span>
              </div>
            </li>
          </ul>
        </div>
      </aside>

      {/* 右侧登录表单 */}
      <main className="login-form-panel">
        <div className="login-card">
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
                  placeholder="请输入用户名"
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
                  placeholder="请输入密码"
                  aria-invalid={errors.password ? 'true' : 'false'}
                />
                <button
                  type="button"
                  className="login-toggle-pwd"
                  onClick={() => setShowPassword((s) => !s)}
                  aria-label={showPassword ? '隐藏密码' : '显示密码'}
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
                忘记密码？
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
                  <span>{t('login.submitting') || '登录中...'}</span>
                </>
              ) : (
                t('login.submit')
              )}
            </button>
          </form>

          <footer className="login-card-footer">
            <span>登录即表示同意</span>
            <a href="#terms" onClick={(e) => e.preventDefault()}>服务条款</a>
            <span>与</span>
            <a href="#privacy" onClick={(e) => e.preventDefault()}>隐私政策</a>
          </footer>
        </div>
      </main>
    </div>
  )
}
