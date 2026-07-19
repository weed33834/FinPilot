import { api } from './client'

export interface FactorResult {
  name: string
  category: string
  values: Record<string, number>
  ic: number
  ir: number
  ic_win_rate: number
  ic_mean: number
  ic_std: number
  rank: number
  description: string
}

export interface MineFactorsRequest {
  financial_data: Array<Record<string, unknown>>
  forward_returns?: Record<string, number>
}

export interface MineFactorsResponse {
  factors: FactorResult[]
  best_factors: FactorResult[]
  summary: string
}

export interface FactorCategory {
  name: string
  factors: string[]
}

export interface FactorCategoriesResponse {
  categories: FactorCategory[]
}

/** 提交财务数据，挖掘候选因子并返回 IC/IR 等评估指标 */
export async function mineFactors(req: MineFactorsRequest) {
  const res = await api.post<MineFactorsResponse>('/factor-mining/mine', req)
  return res
}

/** 获取因子分类目录 */
export async function getFactorCategories() {
  const res = await api.get<FactorCategoriesResponse>('/factor-mining/factor-categories')
  return res
}
