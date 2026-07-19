import axios from 'axios'

// 提取后端错误信息：优先 message/detail，再按状态码兜底
export function getErrorMessage(err: unknown, fallback = '操作失败，请稍后重试'): string {
  if (axios.isAxiosError(err)) {
    const data = err.response?.data
    // 业务错误 {"message": "..."} 或 FastAPI HTTPException {"detail": "..."}
    const message = data?.message ?? data?.detail
    if (typeof message === 'string') {
      return message
    }
    // FastAPI 422 验证错误 {"detail": [{"msg": "..."}, ...]}
    if (Array.isArray(data?.detail) && data.detail.length > 0) {
      const msgs = data.detail
        .map((e: { msg?: string }) => e.msg)
        .filter((m: unknown): m is string => typeof m === 'string')
      if (msgs.length > 0) {
        return msgs.join('；')
      }
    }
    // 状态码兜底
    const status = err.response?.status
    if (status === 401) return '请重新登录'
    if (status === 403) return '没有权限执行此操作'
    if (status === 404) return '请求的资源不存在'
    if (status === 429) return '请求过于频繁，请稍后再试'
    if (status && status >= 500) return '服务器内部错误，请稍后重试'
    if (err.code === 'ECONNABORTED') return '请求超时，请检查网络后重试'
    if (!err.response) return '网络连接失败，请检查网络设置'
    return fallback
  }
  if (err instanceof Error) {
    return err.message || fallback
  }
  return fallback
}
