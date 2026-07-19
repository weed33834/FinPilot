// 2FA 相关类型，集中定义供 SecurityPage / AuthContext 复用

export interface TwoFAStatus {
  enabled: boolean
  setup_in_progress: boolean
}

export interface TwoFASetup {
  secret: string
  otpauth_uri: string
  qr_svg: string
}

export interface BackupCodesResponse {
  backup_codes: string[]
}

// /auth/login 响应数据：正常签发 access_token 或要求 2FA 二次验证
export interface LoginData {
  access_token?: string
  token_type?: string
  expires_in?: number
  requires_2fa?: boolean
  challenge_token?: string
  challenge_expires_in?: number
}
