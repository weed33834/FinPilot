import Badge from './ui/Badge.tsx'
import EmptyState from './ui/EmptyState.tsx'
import type { Document } from '../types/document'
import { formatDateTime } from '../utils/format.ts'

interface DocumentListProps {
  documents: Document[]
  onSelect: (doc: Document) => void
}

export default function DocumentList({ documents, onSelect }: DocumentListProps) {
  if (documents.length === 0) {
    return (
      <EmptyState
        title="暂无文档"
        description="上传财务报表或凭证文档后，它们会出现在这里。"
      />
    )
  }

  return (
    <div className="table-wrapper">
      <table className="financial">
        <thead>
          <tr>
            <th>文件名</th>
            <th>状态</th>
            <th>置信度</th>
            <th>创建时间</th>
            <th>操作</th>
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
                <button type="button" className="secondary" onClick={() => onSelect(doc)}>
                  查看
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
