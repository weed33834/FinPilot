// LLM 供应商与模型管理类型，与后端 schemas/llm_provider.py 对齐

export type ProviderType = 'ollama' | 'openai'
export type ModelTier = 'low' | 'medium' | 'high'

export interface LlmProvider {
  id: string
  name: string
  provider_type: ProviderType
  base_url: string
  has_api_key: boolean
  is_default: boolean
  is_active: boolean
  last_tested_at: string | null
  last_test_ok: boolean | null
  last_test_message: string | null
  created_at: string | null
  updated_at: string | null
}

export interface LlmModel {
  id: string
  provider_id: string
  model_name: string
  display_name: string
  tier: ModelTier | null
  is_active: boolean
  created_at: string | null
  updated_at: string | null
}

export interface ProviderTestResult {
  ok: boolean
  message: string
  latency_ms: number
  tested_at: string
}

// 创建/更新供应商请求体
export interface ProviderForm {
  name: string
  provider_type: ProviderType
  base_url: string
  api_key: string
  is_default: boolean
  is_active: boolean
}

export interface ModelForm {
  model_name: string
  display_name: string
  tier: ModelTier | ''
  is_active: boolean
}
