import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

function NotFoundPage() {
  const { t } = useTranslation('admin')
  return (
    <div className="container" style={{ textAlign: 'center', paddingTop: '80px' }} role="alert" aria-live="polite">
      <p className="not-found-code">{t('notFound.code')}</p>
      <h1>{t('notFound.title')}</h1>
      <p className="text-muted">{t('notFound.description')}</p>
      <Link to="/agent" className="btn">{t('notFound.backHome')}</Link>
    </div>
  )
}

export default NotFoundPage
