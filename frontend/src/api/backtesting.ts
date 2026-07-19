import { api } from './client'

export type StrategyType = 'sma_cross' | 'momentum' | 'mean_reversion'

export interface BacktestConfig {
  initial_capital: number
  strategy_type: StrategyType
  period_days: number
  params?: Record<string, unknown>
}

export interface EquityPoint {
  date: string
  value: number
}

export interface BacktestResult {
  total_return: number
  annual_return: number
  sharpe_ratio: number
  max_drawdown: number
  alpha: number
  beta: number
  volatility: number
  win_rate: number
  equity_curve: EquityPoint[]
  trade_log: Array<Record<string, unknown>>
}

export interface StrategyInfo {
  type: string
  name: string
  description: string
}

export interface StrategiesResponse {
  strategies: StrategyInfo[]
}

export interface MockDataResponse {
  prices: number[]
  dates: string[]
}

/** 运行策略回测，返回收益、风险指标与净值曲线 */
export async function runBacktest(config: BacktestConfig, prices: number[], dates: string[]) {
  const res = await api.post<BacktestResult>('/backtesting/run', { config, prices, dates })
  return res
}

/** 获取可用策略列表 */
export async function getStrategies() {
  const res = await api.get<StrategiesResponse>('/backtesting/strategies')
  return res
}

/** 生成模拟行情数据（价格序列 + 日期序列） */
export async function generateMockData(nDays = 252) {
  const res = await api.post<MockDataResponse>('/backtesting/generate-mock-data', { n_days: nDays })
  return res
}
