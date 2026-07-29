import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { api } from '../../api/client'
import { getErrorMessage } from '../../utils/errors'
import type { Document } from '../../types/document'
import type { DataResponse } from '../../types/report'
import { ICONS } from '../../components/ui/Icons'
import Badge from '../../components/ui/Badge'
import MobilePageHeader from '../../components/mobile/MobilePageHeader'
import '../../i18n/mobile'

const STATUS_KEY: Record<string, string> = {
  pending: 'common:documents.statusPending',
  processing: 'common:documents.statusProcessing',
  success: 'common:documents.statusSuccess',
  failed: 'common:documents.statusFailed',
  needs_review: 'common:documents.statusNeedsReview',
}

/**
 * 移动端文档详情：单列信息卡 + 返回，复用桌面 /documents/:id 接口。
 * 与桌面 Modal 详情不同，移动端为整页视图，更适合小屏阅读长文本。
 */
export default function DocumentDetailMobile({ id }: { id: string }) {
  const { t } = useTranslation(['common', 'mobile'])
  const navigate = useNavigate()
  const [doc, setDoc] = useState<Document | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError('')
    void api
      .get<DataResponse<Document>>(`/documents/${id}`)
      .then((res) => {
        if (!cancelled) setDoc(res.data.data)
      })
      .catch((err) => {
        if (!cancelled) setError(getErrorMessage(err, t('common:documents.loadFailed')))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [id, t])

  return (
    <div className="mdetail">
      <MobilePageHeader
        title={doc?.filename || t('common:documents.title')}
        onBack={() => navigate('/documents')}
      />

      {loading ? (
        <div className="mdetail__loading">{t('common:status.loading')}</div>
      ) : error ? (
        <div className="mdetail__error" role="alert">
          <span>{error}</span>
        </div>
      ) : doc ? (
        <div className="mdetail__body">
          <div className="mdetail__row">
            <span className="mdetail__label">{t('common:documents.detailStatus')}</span>
            <Badge status={doc.status} label={t(STATUS_KEY[doc.status] || 'common:documents.statusPending')} />
          </div>

          {doc.confidence !== null && doc.confidence !== undefined && (
            <div className="mdetail__row">
              <span className="mdetail__label">{t('common:documents.detailConfidence')}</span>
              <span>{(doc.confidence * 100).toFixed(0)}%</span>
            </div>
          )}

          {doc.created_at && (
            <div className="mdetail__row">
              <span className="mdetail__label">{t('common:documents.detailCreatedAt')}</span>
              <span>{new Date(doc.created_at).toLocaleString()}</span>
            </div>
          )}

          {doc.error_message && (
            <div className="mdetail__alert" role="alert">
              <strong>{t('common:documents.detailError')}</strong>
              {doc.error_message}
            </div>
          )}

          {doc.parse_result && (
            <div className="mdetail__block">
              <span className="mdetail__label">{t('common:documents.detailParseResult')}</span>
              <pre className="mdetail__code">{JSON.stringify(doc.parse_result, null, 2)}</pre>
            </div>
          )}

          <button type="button" className="mdetail__back" onClick={() => navigate('/documents')}>
            <ICONS.close size={16} />
            {t('mobile:back')}
          </button>
        </div>
      ) : null}
    </div>
  )
}
