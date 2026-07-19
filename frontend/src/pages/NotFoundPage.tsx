import { Link } from 'react-router-dom'

function NotFoundPage() {
  return (
    <div className="container" style={{ textAlign: 'center', paddingTop: '80px' }}>
      <p style={{ fontSize: '72px', fontWeight: 700, color: 'var(--primary)', margin: 0, lineHeight: 1 }}>404</p>
      <h1 style={{ marginTop: '16px' }}>页面未找到</h1>
      <p className="text-muted" style={{ marginBottom: '24px' }}>您访问的页面不存在或已被移除。</p>
      <Link to="/dashboard" className="btn" style={{ display: 'inline-block' }}>
        返回首页
      </Link>
    </div>
  )
}

export default NotFoundPage
