// 自然语言查询结果（对应后端 NLQueryResponse）
export interface NLQueryResult {
  question: string
  sql: string | null
  data: Array<Record<string, unknown>>
  execution_time_ms: number | null
  confidence: number | null
  backend: string | null
  explanation: string | null
  error: string | null
}

// 本地保留的查询历史条目
export interface QueryHistoryItem {
  question: string
  createdAt: string
  ok: boolean
}
