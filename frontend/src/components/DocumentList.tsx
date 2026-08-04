import { useTranslation } from 'react-i18next'
import Badge from './ui/Badge.tsx'
import EmptyState from './ui/EmptyState.tsx'
import type { Document } from '../types/document'
import { formatDateTime } from '../utils/format.ts'

interface DocumentListProps {
  documents: Document[]
  onSelect: (doc: Document) => void
  onDelete?: (doc: Document) => void
}

export default function DocumentList({ documents, onSelect, onDelete }: DocumentListProps) {
  const { t } = useTranslation()
  if (documents.length === 0) {
    return (
      <EmptyState
        icon="documents"
        title={t('common:documents.emptyTitle')}
        description={t('common:documents.emptyDesc')}
      />
    )
  }

  return (
    <div className="table-wrapper">
      <table className="financial">
        <thead>
          <tr>
            <th>{t('common:documents.colFilename')}</th>
            <th>{t('common:documents.colStatus')}</th>
            <th>{t('common:documents.colConfidence')}</th>
            <th>{t('common:documents.colCreatedAt')}</th>
            <th>{t('common:documents.colActions')}</th>
          </tr>
        </thead>
        <tbody>
          {documents.map((doc) => (
            <tr key={doc.id}>
              <td>{doc.filename}</td>
              <td>
                <Badge status={doc.status} />
              </td>
              <td className="num">
                {doc.confidence !== null && doc.confidence !== undefined
                  ? `${(doc.confidence * 100).toFixed(0)}%`
                  : '—'}
              </td>
              <td>{formatDateTime(doc.created_at)}</td>
              <td>
                <div className="action-group">
                  <button type="button" className="secondary" onClick={() => onSelect(doc)}>
                    {t('common:actions.view')}
                  </button>
                  {onDelete && (
                    <button
                      type="button"
                      className="secondary"
                      style={{ color: 'var(--color-danger, #dc2626)' }}
                      onClick={() => onDelete(doc)}
                    >
                      {t('common:actions.delete')}
                    </button>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
