import { Component } from 'react'
import type { ErrorInfo, ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { captureException } from '../observability.ts'
import i18n from '../i18n/config.ts'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

// 全局错误边界：捕获子树渲染错误，渲染兜底页避免整页白屏
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('ErrorBoundary 捕获到渲染错误：', error, info)
    captureException(error, { componentStack: info.componentStack })
  }

  handleReload = () => {
    window.location.reload()
  }

  render() {
    if (this.state.hasError) {
      const summary = this.state.error?.message || i18n.t('common:errorBoundary.unknownError')
      return (
        <div className="login-page">
          <div className="login-card" style={{ maxWidth: 420, width: '100%' }}>
            <h2 className="login-card-title">{i18n.t('common:errorBoundary.title')}</h2>
            <p className="login-card-sub">{i18n.t('common:errorBoundary.description')}</p>
            <div className="alert alert-error mb-4" role="alert">
              {summary}
            </div>
            <button type="button" className="login-submit" onClick={this.handleReload}>
              {i18n.t('common:errorBoundary.refreshPage')}
            </button>
            <Link
              to="/dashboard"
              className="btn btn-secondary"
              style={{ width: '100%', marginTop: '0.5rem' }}
            >
              {i18n.t('common:errorBoundary.backToDashboard')}
            </Link>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
