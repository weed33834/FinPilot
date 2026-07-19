export interface Document {
  id: string
  filename: string
  status: 'pending' | 'processing' | 'success' | 'failed' | 'needs_review'
  confidence: number | null
  parse_result: Record<string, unknown> | null
  error_message: string | null
  created_at: string
}
