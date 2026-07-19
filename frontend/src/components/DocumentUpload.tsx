import { useRef, useState, type ChangeEvent, type FormEvent } from 'react'
import { api } from '../api/client'
import { getErrorMessage } from '../utils/errors'
import type { Document } from '../types/document'
import type { DataResponse } from '../types/report'

interface DocumentUploadProps {
  onUploaded: (doc: Document) => void
}

export default function DocumentUpload({ onUploaded }: DocumentUploadProps) {
  const [file, setFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleChange = (e: ChangeEvent<HTMLInputElement>) => {
    setError('')
    if (e.target.files && e.target.files.length > 0) {
      setFile(e.target.files[0])
    }
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!file) {
      setError('请选择文件')
      return
    }

    const allowedExtensions = ['csv', 'xlsx', 'xls', 'pdf']
    const ext = file.name.split('.').pop()?.toLowerCase()
    if (!ext || !allowedExtensions.includes(ext)) {
      setError(`仅支持 ${allowedExtensions.join('/')} 文件`)
      return
    }

    setUploading(true)
    setError('')

    const formData = new FormData()
    formData.append('file', file)

    try {
      const response = await api.post<DataResponse<Document>>('/documents/upload', formData)
      if (response.data.data) onUploaded(response.data.data)
      setFile(null)
      if (fileInputRef.current) fileInputRef.current.value = ''
    } catch (err) {
      setError(getErrorMessage(err, '上传失败，请检查文件格式和权限'))
    } finally {
      setUploading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <div className="file-input">
        <button
          type="button"
          className="secondary"
          onClick={() => fileInputRef.current?.click()}
          disabled={uploading}
        >
          {file ? '重新选择' : '选择文件'}
        </button>
        <span className="file-name" style={{ marginLeft: '8px' }}>
          {file ? file.name : '未选择文件'}
        </span>
        <input
          ref={fileInputRef}
          id="file-input"
          type="file"
          accept=".csv,.xlsx,.xls,.pdf"
          onChange={handleChange}
          disabled={uploading}
          style={{ display: 'none' }}
        />
        <button type="submit" disabled={uploading || !file}>
          {uploading ? '上传中...' : '上传并解析'}
        </button>
      </div>
      {error && (
        <div className="alert alert-error" role="alert">
          {error}
        </div>
      )}
    </form>
  )
}
