import { api } from './client.ts'
import type {
  KpiOverview,
  MetricTrend,
  MetricComparison,
  DrillDown,
} from '../types/metric.ts'

export async function getKpiOverview(
  year: number,
  period: string,
): Promise<KpiOverview> {
  const resp = await api.get('/metrics/overview', { params: { year, period } })
  return resp.data.data as KpiOverview
}

export async function getMetricTrend(
  metric: string,
  years: number[],
): Promise<MetricTrend> {
  const resp = await api.get(`/metrics/${metric}/trend`, {
    params: { years: years.join(',') },
  })
  return resp.data.data as MetricTrend
}

export async function getMetricComparison(
  year: number,
  periods: string[],
): Promise<MetricComparison> {
  const resp = await api.get('/metrics/comparison', {
    params: { year, periods: periods.join(',') },
  })
  return resp.data.data as MetricComparison
}

export async function getDrillDown(
  metric: string,
  year: number,
  period?: string,
): Promise<DrillDown> {
  const resp = await api.get(`/metrics/${metric}/drill-down`, {
    params: { year, period },
  })
  return resp.data.data as DrillDown
}
