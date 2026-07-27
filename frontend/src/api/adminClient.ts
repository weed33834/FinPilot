import axios from 'axios'
import { useAuthStore } from '../stores/authStore'

/** 管理后台专用 API 客户端 — 与主 API 客户端统一使用环境变量配置 baseURL */
export const adminApi = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 30000,
  withCredentials: true,
})

adminApi.interceptors.response.use(
  (response) => response,
  (error) => {
    if (axios.isAxiosError(error) && error.response?.status === 401) {
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
