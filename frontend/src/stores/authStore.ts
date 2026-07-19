import { create } from 'zustand'
import { api } from '../api/client.ts'
import { setUserContext, clearUserContext } from '../observability.ts'
import type { DataResponse } from '../types/report.ts'
import type { LoginData } from '../types/twoFactor.ts'

export interface LoginResult {
  requires2fa: boolean
  challengeToken?: string
}

interface MeResponse {
  id?: string
  role: string
  username: string
}

interface AuthState {
  isAuthenticated: boolean
  loading: boolean
  role: string | null
  username: string | null
  userId: string | null

  // actions
  fetchMe: () => Promise<void>
  login: (username: string, password: string, rememberMe?: boolean) => Promise<LoginResult>
  verify2fa: (challengeToken: string, totpCode?: string, backupCode?: string) => Promise<void>
  loginWithOAuth: (provider: string) => void
  completeOAuthCallback: () => Promise<void>
  logout: () => Promise<void>
  unauthorize: () => void
}

export const useAuthStore = create<AuthState>((set, get) => ({
  isAuthenticated: false,
  loading: true,
  role: null,
  username: null,
  userId: null,

  fetchMe: async () => {
    const meResponse = await api.get<DataResponse<MeResponse>>('/auth/me')
    const userRole = meResponse.data.data.role
    const userName = meResponse.data.data.username
    const userId = meResponse.data.data.id ?? null
    if (!userRole || !userName) throw new Error('用户信息响应异常')
    setUserContext({ id: userId ?? userName, username: userName, role: userRole })
    set({ isAuthenticated: true, role: userRole, username: userName, userId })
  },

  login: async (username, password, rememberMe) => {
    const response = await api.post<DataResponse<LoginData>>('/auth/login', {
      username,
      password,
      remember_me: rememberMe ?? false,
    })
    const data = response.data.data

    if (data?.requires_2fa) {
      return { requires2fa: true, challengeToken: data.challenge_token }
    }
    if (!data?.access_token) throw new Error('登录响应异常')
    await get().fetchMe()
    return { requires2fa: false }
  },

  verify2fa: async (challengeToken, totpCode, backupCode) => {
    await api.post<DataResponse<LoginData>>('/auth/verify-2fa', {
      challenge_token: challengeToken,
      totp_code: totpCode || undefined,
      backup_code: backupCode || undefined,
    })
    await get().fetchMe()
  },

  loginWithOAuth: (provider) => {
    window.location.href = `/api/v1/auth/oauth/${provider}/login`
  },

  completeOAuthCallback: async () => {
    await get().fetchMe()
  },

  logout: async () => {
    try {
      await api.post('/auth/logout')
    } catch {
      // 忽略
    }
    clearUserContext()
    set({ isAuthenticated: false, role: null, username: null, userId: null })
  },

  unauthorize: () => {
    clearUserContext()
    set({ isAuthenticated: false, role: null, username: null, userId: null })
  },
}))
