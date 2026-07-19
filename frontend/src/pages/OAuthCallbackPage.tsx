import { useState, useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../context/AuthContext.tsx'

export default function OAuthCallbackPage() {
  const { t } = useTranslation('auth')
  const navigate = useNavigate()
  const { completeOAuthCallback } = useAuth()
  const [searchParams] = useSearchParams()
  const [error, setError] = useState<string | null>(null)
  const [processing, setProcessing] = useState(true)

  useEffect(() => {
    // 新流程：?status=success 或 ?error=...
    const statusParam = searchParams.get('status')
    const errorMsg = searchParams.get('error')
    // 旧流程兼容：#token=... 或 #error=...
    const hash = window.location.hash.replace(/^#/, '')
    const hashParams = new URLSearchParams(hash)
    const legacyToken = hashParams.get('token')
    const legacyError = hashParams.get('error')

    if (errorMsg || legacyError) {
      setError(errorMsg || legacyError || t('oauth.callbackFailed'))
      setProcessing(false)
      return
    }
    if (statusParam === 'success' || legacyToken) {
      let cancelled = false
      // cookie 已由后端 Set-Cookie 设置；旧 #token 流程无法重建 cookie，
      // 这里仍触发 /auth/me 探测会话，失败则提示
      completeOAuthCallback()
        .then(() => {
          if (!cancelled) navigate('/dashboard', { replace: true })
        })
        .catch(() => {
          if (!cancelled) {
            setError(t('oauth.sessionFailed'))
            setProcessing(false)
          }
        })
      return () => {
        cancelled = true
      }
    }
    setError(t('login.missingCredential'))
    setProcessing(false)
  }, [completeOAuthCallback, navigate, searchParams, t])

  if (processing) {
    return (
      <div className="login-page">
        <div className="login-card">
          <h1>{t('oauth.processing')}</h1>
          <p className="login-subtitle">{t('oauth.processingSubtitle')}</p>
          <div className="skeleton skeleton-line" />
        </div>
      </div>
    )
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <h1>{t('oauth.failed')}</h1>
        <p className="login-subtitle">{error}</p>
        <button type="button" onClick={() => navigate('/login', { replace: true })}>
          {t('login.backToLogin')}
        </button>
      </div>
    </div>
  )
}
