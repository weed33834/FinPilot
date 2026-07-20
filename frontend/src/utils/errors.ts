import axios from 'axios'

/**
 * 自定义 fetch 错误：携带 HTTP 状态码、URL、方法、响应体文本。
 * 用于 SSE / fetch 调用失败时，让错误系统能像 axios 错误一样精确报错。
 */
export class FetchError extends Error {
  readonly status: number
  readonly url: string
  readonly method: string
  readonly bodyText: string
  readonly code?: string

  constructor(args: {
    message?: string
    status?: number
    url?: string
    method?: string
    bodyText?: string
    code?: string
  }) {
    super(args.message || 'fetch 请求失败')
    this.name = 'FetchError'
    this.status = args.status ?? 0
    this.url = args.url || ''
    this.method = (args.method || 'GET').toUpperCase()
    this.bodyText = args.bodyText || ''
    this.code = args.code
  }
}

/**
 * 把任意错误统一格式化为可读字符串，并尽量精确指出**到底是哪里出错**。
 *
 * 输出格式（带来源标签 + 状态码 + 后端原因）：
 *   [GET /model-configs] 404 路由不存在或后端未实现 — detail
 *   [POST /queries/nl2sql] 500 服务器内部错误 — KeyError 'foo'
 *   [network] 请求超时（30s）— 后端未在规定时间内响应
 *
 * 设计目标：
 * - 用户能一眼看到「是哪个接口」「什么状态码」「后端说为什么」
 * - 不再是「操作失败，请稍后重试」这种 0 信息量的兜底
 */
export function getErrorMessage(err: unknown, fallback = '操作失败，请稍后重试'): string {
  if (axios.isAxiosError(err)) {
    return _formatAxiosError(err)
  }
  if (err instanceof FetchError) {
    return _formatFetchError(err)
  }
  if (err instanceof DOMException && err.name === 'AbortError') {
    return '[abort] 请求已取消'
  }
  // 浏览器原生的 fetch 网络错误（无法连接）是 TypeError
  if (err instanceof TypeError && /fetch|network|Failed to fetch/i.test(err.message)) {
    return `[network] 无法连接到后端服务 — ${err.message}（后端可能未启动 / 已崩溃 / CORS 拒绝）`
  }
  if (err instanceof Error) {
    // 兜底：原生 Error 仅暴露 message，但仍是可读信息
    return err.message || fallback
  }
  if (typeof err === 'string') return err
  return fallback
}

/**
 * 把 FetchError 格式化为「[METHOD /url] STATUS 标签 — detail」的精确字符串。
 * 与 _formatAxiosError 保持一致的输出风格。
 */
function _formatFetchError(err: FetchError): string {
  const fullURL = err.url.replace(/\/api\/v1/, '') || '/'
  const tag = `[${err.method} ${fullURL}]`

  // 无 status —— 网络层错误
  if (!err.status) {
    if (err.code === 'ECONNABORTED' || /timeout|aborted/i.test(err.message)) {
      return `[network] 请求超时 — 后端未在规定时间内响应（LLM 推理过慢 / 后端阻塞）`
    }
    if (err.code === 'ERR_NETWORK' || /Failed to fetch|NetworkError/i.test(err.message)) {
      return `[network] 网络连接失败 — 无法连接到后端服务（可能未启动 / CORS 拒绝 / 服务已挂）`
    }
    return `[network] ${err.message || '未知网络错误'}`
  }

  const status = err.status
  const statusLabel = _statusLabel(status)
  // 尝试从响应体解析 detail/message
  let detail = ''
  try {
    const data = JSON.parse(err.bodyText)
    detail = _extractBackendDetail(data)
    // 422 验证错误：把字段级错误拼进去
    if (status === 422 && Array.isArray(data?.detail)) {
      const fieldErrs = (data.detail as Array<Record<string, unknown>>)
        .map((e) => {
          const loc = Array.isArray(e.loc) ? e.loc.join('.') : ''
          const msg = typeof e.msg === 'string' ? e.msg : ''
          return loc ? `${loc}: ${msg}` : msg
        })
        .filter(Boolean)
        .join('；')
      return `${tag} 422 参数校验失败 — ${fieldErrs || '请检查请求体'}`
    }
  } catch {
    // 响应体不是 JSON，直接用文本
    detail = err.bodyText || ''
  }

  if (detail) return `${tag} ${status} ${statusLabel} — ${detail}`
  return `${tag} ${status} ${statusLabel}`
}

/**
 * 把 axios 错误格式化为「[METHOD /url] STATUS — detail」的精确字符串。
 *
 * - 优先用后端 detail/message；422 验证错误把字段名拼进去
 * - 网络层错误（无 response）按 err.code 分类：超时 / 拒绝 / DNS / 未知
 * - 始终带 METHOD + URL，让用户/管理员看到具体哪个端点
 */
function _formatAxiosError(err: import('axios').AxiosError): string {
  const method = (err.config?.method || 'GET').toUpperCase()
  // baseURL 已是 /api/v1，url 是相对路径；显示完整相对路径即可定位
  const baseURL = err.config?.baseURL || ''
  const url = err.config?.url || ''
  // 去掉重复前缀，让显示更短
  const fullURL = url.startsWith('http') ? url : (baseURL + url).replace(/\/api\/v1/, '') || '/'
  const tag = `[${method} ${fullURL}]`

  // 1. 有 HTTP 响应 —— 优先用后端 detail/message
  if (err.response) {
    const status = err.response.status
    const data = err.response.data as Record<string, unknown> | undefined
    const detail = _extractBackendDetail(data)
    const statusLabel = _statusLabel(status)

    // 422 验证错误：把字段级错误拼进去，让用户知道哪个字段错了
    if (status === 422 && Array.isArray(data?.detail)) {
      const fieldErrs = (data.detail as Array<Record<string, unknown>>)
        .map((e) => {
          const loc = Array.isArray(e.loc) ? e.loc.join('.') : ''
          const msg = typeof e.msg === 'string' ? e.msg : ''
          return loc ? `${loc}: ${msg}` : msg
        })
        .filter(Boolean)
        .join('；')
      return `${tag} 422 参数校验失败 — ${fieldErrs || '请检查请求体'}`
    }

    if (detail) {
      return `${tag} ${status} ${statusLabel} — ${detail}`
    }
    return `${tag} ${status} ${statusLabel}`
  }

  // 2. 无 HTTP 响应 —— 网络层错误（超时 / 拒绝 / DNS / CORS / 中断）
  const code = err.code || ''
  if (code === 'ECONNABORTED') {
    const timeout = err.config?.timeout ? `${Math.round(err.config.timeout / 1000)}s` : ''
    return `[network] 请求超时${timeout ? `（${timeout}）` : ''} — 后端未在规定时间内响应，可能是 LLM 推理过慢或后端阻塞`
  }
  if (code === 'ERR_NETWORK') {
    return `[network] 网络连接失败 — 无法连接到后端服务（可能未启动 / CORS 拒绝 / 服务已挂）`
  }
  if (code === 'ECONNREFUSED') {
    return `[network] 连接被拒绝 — 后端服务未在监听该端口`
  }
  if (code === 'ENOTFOUND') {
    return `[network] 域名解析失败 — 无法解析后端地址`
  }
  if (code === 'ECONNRESET') {
    return `[network] 连接被重置 — 后端可能崩溃或被代理截断`
  }
  if (code) {
    return `[network] ${code} — ${err.message || '网络异常'}`
  }
  return `[network] ${err.message || '未知网络错误'}`
}

/**
 * 从后端响应体中提取人类可读的错误细节。
 * 兼容多种后端响应格式：
 * - FastAPI HTTPException: {"detail": "..."}
 * - 业务错误: {"message": "..."}
 * - 包装响应: {"code": 1, "message": "...", "data": null}
 * - 嵌套: {"error": {"message": "..."}}
 */
function _extractBackendDetail(data: unknown): string {
  if (!data) return ''
  if (typeof data === 'string') return data
  if (typeof data !== 'object') return String(data)

  const obj = data as Record<string, unknown>
  // FastAPI HTTPException
  if (typeof obj.detail === 'string') return obj.detail
  // 业务错误
  if (typeof obj.message === 'string' && obj.message) return obj.message
  // 包装响应 code!=0
  if (typeof obj.message === 'string' && obj.code && obj.code !== 0) return obj.message
  // 嵌套 error.message
  if (obj.error && typeof obj.error === 'object') {
    const inner = (obj.error as Record<string, unknown>).message
    if (typeof inner === 'string') return inner
  }
  // error 字段是字符串
  if (typeof obj.error === 'string') return obj.error
  return ''
}

/** 给 HTTP 状态码加一句中文标签，让用户立刻知道是什么类型错误 */
function _statusLabel(status: number): string {
  if (status === 400) return '请求参数错误'
  if (status === 401) return '未登录或会话已过期'
  if (status === 403) return '没有权限执行此操作'
  if (status === 404) return '路由不存在或后端未实现'
  if (status === 405) return '请求方法不被允许'
  if (status === 409) return '资源冲突'
  if (status === 413) return '请求体过大'
  if (status === 422) return '参数校验失败'
  if (status === 429) return '请求过于频繁'
  if (status === 500) return '服务器内部错误'
  if (status === 501) return '功能尚未实现'
  if (status === 502) return '网关错误'
  if (status === 503) return '服务不可用'
  if (status === 504) return '网关超时'
  if (status >= 500) return '服务器错误'
  if (status >= 400) return '请求错误'
  return ''
}

/**
 * 把错误分类成 4 个 level：network / auth / client / server / unknown。
 * 用于前端按级别上色（network=灰、auth=黄、client=橙、server=红）。
 */
export type ErrorLevel = 'network' | 'auth' | 'client' | 'server' | 'unknown'

export function getErrorLevel(err: unknown): ErrorLevel {
  if (err instanceof FetchError) {
    if (!err.status) return 'network'
    if (err.status === 401 || err.status === 403) return 'auth'
    if (err.status >= 500) return 'server'
    if (err.status >= 400) return 'client'
    return 'unknown'
  }
  if (axios.isAxiosError(err)) {
    if (!err.response) return 'network'
    const s = err.response.status
    if (s === 401 || s === 403) return 'auth'
    if (s >= 500) return 'server'
    if (s >= 400) return 'client'
    return 'unknown'
  }
  if (err instanceof DOMException && err.name === 'AbortError') return 'network'
  if (err instanceof TypeError && /fetch|network|Failed to fetch/i.test(err.message)) {
    return 'network'
  }
  return 'unknown'
}

/**
 * 返回错误的简短类型标签（用于错误条上的小标签）。
 */
export function getErrorLevelLabel(level: ErrorLevel): string {
  switch (level) {
    case 'network': return '网络'
    case 'auth': return '权限'
    case 'client': return '请求'
    case 'server': return '服务'
    default: return '错误'
  }
}
