import axios from 'axios'

/** 管理后台专用 API 客户端 — 与主 API 客户端统一使用 /api/v1 前缀 */
export const adminApi = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  withCredentials: true,
})

adminApi.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (axios.isAxiosError(error) && error.response?.status === 401) {
      const url = error.config?.url || ''
      const safe401Urls = ['/auth/login', '/auth/verify-2fa', '/auth/change-password', '/auth/oauth/', '/auth/me']
      const isSafe = safe401Urls.some((u) => {
        if (u.endsWith('/')) return url.includes(u)
        return url.endsWith(u)
      })
      if (!isSafe) {
        // Trigger global logout via auth store
        try {
          const { useAuthStore } = await import('../stores/authStore.ts')
          useAuthStore.getState().unauthorize()
        } catch {
          // auth store may not be available
        }
      }
    }
    return Promise.reject(error)
  },
)
