/** 统一 API 响应类型 */
export interface ApiResponse<T = unknown> {
  code: number
  message: string
  data: T
}

/** 统一分页数据类型 */
export interface PaginatedData<T> {
  total: number
  page: number
  page_size: number
  items: T[]
}

/** 统一分页响应 */
export type PaginatedResponse<T> = ApiResponse<PaginatedData<T>>
