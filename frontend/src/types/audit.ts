export interface AuditLog {
  id: string
  timestamp: string
  tenant_id: string
  user_id: string | null
  action: string
  resource: string
  result: string | null
  ip: string | null
  reason: string | null
}
