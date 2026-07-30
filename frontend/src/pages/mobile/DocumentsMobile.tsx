import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { api } from '../../api/client'
import { getErrorMessage } from '../../utils/errors'
import type { Document } from '../../types/document'
import type { DataResponse, PaginatedResponse } from '../../types/report'
import DocumentUpload from '../../components/DocumentUpload'
import { ICONS } from '../../components/ui/Icons'
import MobilePageHeader from '../../components/mobile/MobilePageHeader'
import BottomSheet from '../../components/mobile/BottomSheet'
import MobileCard from '../../components/mobile/MobileCard'
import '../../i18n/mobile'

const STATUS_KEY: Record<string, string> = {
  pending: 'common:documents.statusPending',
  processing: 'common:documents.statusProcessing',
  success: 'common:documents.statusSuccess',
  failed: 'common:documents.statusFailed',
  needs_review: 'common:documents.statusNeedsReview',
}

/**
 * 移动端文档：单列卡片列表 + 底部上传弹层（与桌面双栏/表格完全不同的交互）。
 * 点击卡片进入 /documents/:id 复用桌面详情路由。
 */
export default function DocumentsMobile() {
  const { t } = useTranslation(['common', 'mobile'])
  const navigate = useNavigate()
  const [documents, setDocuments] = useState<Document[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [uploadOpen, setUploadOpen] = useState(false)

  const fetchDocuments = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const response = await api.get<DataResponse<PaginatedResponse<Document>>>('/documents', {
        params: { page: 1, page_size: 50 },
      })
      setDocuments(response.data.data?.items || [])
    } catch (err) {
      setError(getErrorMessage(err, t('common:documents.loadFailed')))
    } finally {
      setLoading(false)
    }
  }, [t])

  useEffect(() => {
    void fetchDocuments()
  }, [fetchDocuments])

  return (
    <div className="mdocs">
      <MobilePageHeader
        title={t('common:documents.title')}
        right={
          <button
            type="button"
            className="mdocs__add"
            aria-label={t('common:actions.upload')}
            onClick={() => setUploadOpen(true)}
          >
            <ICONS.download size={18} />
          </button>
        }
      />

      {error && (
        <div className="mdocs__error" role="alert">
          <span>{error}</span>
          <button type="button" onClick={fetchDocuments}>
            {t('common:actions.retry')}
          </button>
        </div>
      )}

      {loading ? (
        <div className="mdocs__loading">{t('common:status.loading')}</div>
      ) : documents.length === 0 ? (
        <div className="mdocs__empty">
          <ICONS.documents size={28} />
          <p>{t('common:documents.emptyTitle')}</p>
        </div>
      ) : (
        <div className="mdocs__list">
          {documents.map((doc) => (
            <MobileCard
              key={doc.id}
              onClick={() => navigate(`/documents/${doc.id}`)}
            >
              <div className="mdocs__item-head">
                <span className="mdocs__name">{doc.filename}</span>
                <span className="mdocs__status">
                  {t(STATUS_KEY[doc.status] || 'common:documents.statusPending')}
                </span>
              </div>
              <div className="mdocs__meta">
                {doc.created_at ? new Date(doc.created_at).toLocaleDateString() : ''}
              </div>
            </MobileCard>
          ))}
        </div>
      )}

      <BottomSheet
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        title={t('common:actions.upload')}
      >
        <DocumentUpload onUploaded={() => { setUploadOpen(false); void fetchDocuments() }} />
      </BottomSheet>
    </div>
  )
}
