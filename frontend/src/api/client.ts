import axios from 'axios'
import { useAuthStore } from '../stores/authStore.ts'

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 30000,
  // 自动发送 HttpOnly auth cookie；token 不再存 localStorage，缓解 XSS 窃取
  withCredentials: true,
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (axios.isAxiosError(error) && error.response?.status === 401) {
      // 登录 / 2FA 验证 / 改密 / OAuth / me 探测 端点的 401 是凭据错误，不触发全局登出
      const url = error.config?.url || ''
      const safe401Urls = ['/auth/login', '/auth/verify-2fa', '/auth/change-password', '/auth/oauth/', '/auth/me']
      const isSafe = safe401Urls.some((u) => {
        if (u.endsWith('/')) return url.includes(u)
        return url.endsWith(u)
      })
      if (!isSafe) {
        useAuthStore.getState().unauthorize()
      }
    }
    return Promise.reject(error)
  },
)
