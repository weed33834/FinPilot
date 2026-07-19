export interface AccessPolicy {
  id: string
  tenant_id: string
  name: string
  resource_type: string
  action: string
  effect: 'allow' | 'deny'
  priority: number
  conditions: Record<string, unknown> | null
  description: string | null
  is_active: boolean
}

export interface AccessPolicyForm {
  name: string
  resource_type: string
  action: string
  effect: 'allow' | 'deny'
  priority: number
  conditions: string
  description: string
  is_active: boolean
}

export const EMPTY_POLICY_FORM: AccessPolicyForm = {
  name: '',
  resource_type: 'report',
  action: 'read',
  effect: 'allow',
  priority: 100,
  conditions: '',
  description: '',
  is_active: true,
}
