import Badge from './ui/Badge.tsx'
import Modal from './ui/Modal.tsx'
import type { Document } from '../types/document'

interface DocumentDetailProps {
  document: Document
  onClose: () => void
}

export default function DocumentDetail({ document: doc, onClose }: DocumentDetailProps) {
  return (
    <Modal title={doc.filename} onClose={onClose}>
      <div className="detail-grid">
        <div className="detail-group">
          <span className="detail-label">状态</span>
          <div>
            <Badge status={doc.status} />
          </div>
        </div>

        {doc.confidence !== null && doc.confidence !== undefined && (
          <div className="detail-group">
            <span className="detail-label">置信度</span>
            <div>{(doc.confidence * 100).toFixed(0)}%</div>
          </div>
        )}

        {doc.error_message && (
          <div className="alert alert-error" role="alert">
            <strong>错误：</strong>
            {doc.error_message}
          </div>
        )}

        {doc.parse_result && (
          <div className="detail-group">
            <span className="detail-label">解析结果</span>
            <pre className="code-block">
              {JSON.stringify(doc.parse_result, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </Modal>
  )
}
