export interface ApiKey {
  id: string
  tenant_id: string
  user_id: string
  name: string
  scopes: string[]
  is_active: string
  last_used_at: string | null
  first_used_at: string | null
  usage_count: number
  expires_at: string | null
  rotated_from: string | null
  created_at: string | null
  updated_at: string | null
}

// 创建 / 轮换后返回的响应，额外包含一次性明文 key
export interface ApiKeyWithPlain extends ApiKey {
  key: string
}
