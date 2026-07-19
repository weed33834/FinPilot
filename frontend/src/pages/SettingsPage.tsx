import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import Loading from '../components/ui/Loading.tsx'
import { api } from '../api/client.ts'
import { getErrorMessage } from '../utils/errors.ts'
import type { DataResponse } from '../types/report.ts'

type ConfigValue = string | boolean | number
interface SystemConfig {
  [key: string]: ConfigValue
}

// 配置项中文标签（与后端 GET /admin/config 返回字段对应）
const CONFIG_LABELS: Record<string, string> = {
  app_name: '应用名称',
  app_env: '运行环境',
  debug: '调试模式',
  log_level: '日志级别',
  task_backend: '任务后端',
  storage_backend: '存储后端',
  text2sql_backend: 'Text2SQL 后端',
  llm_provider: 'LLM 提供者',
  ollama_host: 'Ollama 地址',
  ollama_model: 'Ollama 模型',
  agent_intent_mode: 'Agent 意图识别模式',
  agent_llm_model: 'Agent LLM 模型',
  rag_chunk_size: 'RAG 切分大小',
  rag_top_k: 'RAG 返回数量',
  rate_limit_enabled: '速率限制',
  rate_limit_max_requests: '速率限制最大请求数',
  rate_limit_window_seconds: '速率限制窗口（秒）',
  redis_configured: 'Redis 已配置',
  celery_configured: 'Celery 已配置',
}

const formatValue = (value: ConfigValue): string => {
  if (typeof value === 'boolean') return value ? '是' : '否'
  return String(value)
}

export default function SettingsPage() {
  const [reloading, setReloading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const queryClient = useQueryClient()

  const {
    data: config,
    isLoading: loading,
    error: configError,
  } = useQuery<SystemConfig | null>({
    queryKey: ['admin-config'],
    queryFn: async () => {
      const response = await api.get<DataResponse<SystemConfig>>('/admin/config')
      return response.data.data ?? null
    },
  })

  const displayError = error || (configError ? getErrorMessage(configError, '加载系统配置失败') : '')

  const handleReload = async () => {
    setReloading(true)
    setError('')
    setSuccess('')
    try {
      await api.post('/admin/reload-config')
      setSuccess('配置已重新加载')
      await queryClient.invalidateQueries({ queryKey: ['admin-config'] })
    } catch (err) {
      setError(getErrorMessage(err, '重载配置失败'))
    } finally {
      setReloading(false)
    }
  }

  const entries = config
    ? Object.entries(CONFIG_LABELS).map(([key, label]) => ({
        key,
        label,
        value: config[key],
      }))
    : []

  return (
    <div className="container">
      <div className="page-header">
        <h1>系统设置</h1>
        <button type="button" onClick={handleReload} disabled={reloading || loading}>
          {reloading ? '重载中...' : '重载配置'}
        </button>
      </div>

      {displayError && (
        <div className="alert alert-error mb-4" role="alert">
          {displayError}
        </div>
      )}
      {success && (
        <div className="alert alert-info mb-4" role="alert">
          {success}
        </div>
      )}

      {loading ? (
        <Loading text="加载系统配置中..." />
      ) : (
        <div className="card">
          <h3 className="card-title">运行配置</h3>
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>配置项</th>
                  <th>当前值</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((item) => (
                  <tr key={item.key}>
                    <td>{item.label}</td>
                    <td>
                      {item.value === undefined ? (
                        <span className="text-muted">—</span>
                      ) : (
                        formatValue(item.value)
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-muted text-sm mt-4">
            以上为非敏感只读配置，敏感信息（密钥、密码等）不在此展示。修改环境变量或 .env 后点击「重载配置」生效。
          </p>
        </div>
      )}
    </div>
  )
}
