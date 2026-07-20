/**
 * 斜杠命令系统 — 在对话界面里调用所有功能来控制整个程序。
 *
 * 设计目标：
 * - 管理员能在对话里调用所有功能（用户管理、模型、审计、审批、订阅、模板等）
 * - 普通用户只能用对话控制普通用户的权限（查询、研报、文档、估值、回测、因子等）
 * - 命令结果是 Markdown 字符串，作为 agent 消息插入到对话流
 * - 错误经统一错误系统（getErrorMessage）格式化为精确报错
 *
 * 用法：
 *   const cmd = parseSlashCommand(input, role)
 *   if (cmd) {
 *     const result = await cmd.handler(args)
 *     // result 是 Markdown 字符串
 *   }
 */

import { api } from '../api/client'
import { adminApi } from '../api/adminClient'
import { getErrorMessage } from './errors'

/** 命令所需角色 */
export type CommandRole = 'user' | 'admin'

/** 命令分类（用于面板分组） */
export type CommandCategory =
  | 'help'
  | 'data'
  | 'report'
  | 'analysis'
  | 'admin'
  | 'system'

/** 命令参数定义（用于面板提示） */
export interface CommandArg {
  name: string
  description: string
  required?: boolean
  default?: string
}

/** 命令定义 */
export interface SlashCommand {
  /** 完整命令名，例如 "models list" */
  name: string
  /** 简短中文描述 */
  description: string
  /** 用法示例 */
  usage: string
  /** 参数定义 */
  args: CommandArg[]
  /** 所需角色 */
  role: CommandRole
  /** 分类 */
  category: CommandCategory
  /** 处理函数：接收解析后的参数，返回 Markdown 字符串 */
  handler: (args: Record<string, string>) => Promise<string>
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

/** 把 API 返回的对象列表渲染为 Markdown 表格 */
function renderTable<T extends Record<string, unknown>>(
  rows: T[],
  columns: Array<{ key: keyof T; label: string; width?: number }>,
): string {
  if (!rows.length) return '_(无数据)_'
  const header = columns.map((c) => c.label).join(' | ')
  const separator = columns.map(() => '---').join(' | ')
  const body = rows
    .map((r) =>
      columns
        .map((c) => {
          const v = r[c.key]
          if (v == null) return '—'
          if (typeof v === 'boolean') return v ? '✓' : '—'
          if (Array.isArray(v)) return v.length ? String(v.length) : '—'
          if (typeof v === 'object') return JSON.stringify(v).slice(0, 40)
          return String(v).slice(0, 60)
        })
        .join(' | '),
    )
    .join('\n')
  return `| ${header} |\n| ${separator} |\n${body
    .split('\n')
    .map((l) => `| ${l} |`)
    .join('\n')}`
}

/** 提取 {code, message, data} 包装响应里的 data 字段 */
function unwrap<T = unknown>(resp: { data: unknown }): T {
  const body = resp.data as { code?: number; data?: T; message?: string }
  if (body && typeof body === 'object' && 'data' in body) {
    return body.data as T
  }
  return resp.data as T
}

/** 统一包装命令执行，把异常转成精确错误消息 */
async function run(fn: () => Promise<string>): Promise<string> {
  try {
    return await fn()
  } catch (err) {
    // 抛出格式化后的错误，由调用方决定如何展示
    throw new Error(getErrorMessage(err, '命令执行失败'))
  }
}

/* ------------------------------------------------------------------ */
/*  命令定义                                                           */
/* ------------------------------------------------------------------ */

const helpCommand: SlashCommand = {
  name: 'help',
  description: '列出当前用户角色可用的所有斜杠命令',
  usage: '/help',
  args: [],
  role: 'user',
  category: 'help',
  handler: async () => {
    // 这里不能直接 import 全局命令表（会循环依赖），由 AgentChatPage 替换
    return '_(命令列表由界面注入)_'
  },
}

/* ----- 数据 / 查询类（user） ----- */

const dashboardCommand: SlashCommand = {
  name: 'dashboard',
  description: '查看个人仪表盘汇总（会话数、文档数、查询数、研报数）',
  usage: '/dashboard',
  args: [],
  role: 'user',
  category: 'data',
  handler: async () =>
    run(async () => {
      const data = unwrap<{ [k: string]: unknown }>(await api.get('/dashboard/summary'))
      const lines = Object.entries(data || {}).map(([k, v]) => `- **${k}**: ${v ?? '—'}`)
      return [`### 个人仪表盘`, '', ...lines].join('\n')
    }),
}

const queriesHistoryCommand: SlashCommand = {
  name: 'queries history',
  description: '查看最近的 NL2SQL 查询历史',
  usage: '/queries history',
  args: [],
  role: 'user',
  category: 'data',
  handler: async () =>
    run(async () => {
      const items = unwrap<Array<{ id?: string; question?: string; created_at?: string }>>(
        await api.get('/queries/history', { params: { limit: 10 } }),
      )
      if (!Array.isArray(items) || !items.length) return '_(暂无查询历史)_'
      const rows = items.map((it, i) => ({
        idx: i + 1,
        question: (it.question || '').slice(0, 50),
        created_at: it.created_at ? new Date(it.created_at).toLocaleString('zh-CN') : '—',
      }))
      return `### 最近查询历史\n\n${renderTable(rows, [
        { key: 'idx', label: '#' },
        { key: 'question', label: '问题' },
        { key: 'created_at', label: '时间' },
      ])}`
    }),
}

const conversationsListCommand: SlashCommand = {
  name: 'conversations list',
  description: '查看当前用户的会话列表',
  usage: '/conversations list',
  args: [],
  role: 'user',
  category: 'data',
  handler: async () =>
    run(async () => {
      const data = unwrap<{ active?: unknown[]; archived?: unknown[] }>(
        await api.get('/conversations'),
      )
      const activeCount = Array.isArray(data?.active) ? data.active.length : 0
      const archivedCount = Array.isArray(data?.archived) ? data.archived.length : 0
      return [
        '### 会话总览',
        '',
        `- 活跃会话：**${activeCount}**`,
        `- 已归档：**${archivedCount}**`,
        '',
        '_提示：在「会话管理」页面查看完整列表与消息内容_',
      ].join('\n')
    }),
}

const documentsListCommand: SlashCommand = {
  name: 'documents list',
  description: '查看已上传的文档列表',
  usage: '/documents list',
  args: [],
  role: 'user',
  category: 'data',
  handler: async () =>
    run(async () => {
      const data = unwrap<{ items?: Array<Record<string, unknown>>; total?: number }>(
        await api.get('/documents'),
      )
      const items = data?.items || []
      if (!items.length) return '_(暂无文档)_'
      const rows = items.slice(0, 10).map((d) => ({
        id: String(d.id ?? '—').slice(0, 8),
        name: String(d.name ?? d.filename ?? '—').slice(0, 30),
        status: String(d.status ?? '—'),
        size: d.size != null ? `${Math.round(Number(d.size) / 1024)}KB` : '—',
      }))
      return `### 文档列表（共 ${data?.total ?? items.length} 个）\n\n${renderTable(rows, [
        { key: 'id', label: 'ID' },
        { key: 'name', label: '名称' },
        { key: 'status', label: '状态' },
        { key: 'size', label: '大小' },
      ])}`
    }),
}

/* ----- 研报类（user） ----- */

const reportsListCommand: SlashCommand = {
  name: 'reports list',
  description: '查看研报列表',
  usage: '/reports list',
  args: [],
  role: 'user',
  category: 'report',
  handler: async () =>
    run(async () => {
      const data = unwrap<{ items?: Array<Record<string, unknown>>; total?: number }>(
        await api.get('/reports', { params: { page: 1, page_size: 10 } }),
      )
      const items = data?.items || []
      if (!items.length) return '_(暂无研报)_'
      const rows = items.map((r) => ({
        id: String(r.id ?? '—').slice(0, 8),
        title: String(r.title ?? '—').slice(0, 40),
        status: String(r.status ?? '—'),
        created_at: r.created_at ? new Date(String(r.created_at)).toLocaleDateString('zh-CN') : '—',
      }))
      return `### 研报列表（共 ${data?.total ?? items.length} 个）\n\n${renderTable(rows, [
        { key: 'id', label: 'ID' },
        { key: 'title', label: '标题' },
        { key: 'status', label: '状态' },
        { key: 'created_at', label: '创建日期' },
      ])}`
    }),
}

const reportsGenerateCommand: SlashCommand = {
  name: 'reports generate',
  description: '触发 equity 研报异步生成（返回 task_id 后可用 /reports status 查询）',
  usage: '/reports generate <ticker> [company]',
  args: [
    { name: 'ticker', description: '股票代码，如 600519', required: true },
    { name: 'company', description: '公司名称（可选）' },
  ],
  role: 'user',
  category: 'report',
  handler: async (args) =>
    run(async () => {
      const ticker = args.ticker
      if (!ticker) throw new Error('请提供股票代码 ticker')
      const body: Record<string, unknown> = { ticker }
      if (args.company) body.company = args.company
      const data = unwrap<{ task_id?: string; status?: string }>(
        await api.post('/reports/generate', body),
      )
      return [
        '### 研报生成任务已提交',
        '',
        `- **task_id**: \`${data.task_id ?? '—'}\``,
        `- **状态**: ${data.status ?? 'pending'}`,
        '',
        '_稍后可用 `/reports status <task_id>` 查询进度_',
      ].join('\n')
    }),
}

const reportsStatusCommand: SlashCommand = {
  name: 'reports status',
  description: '查询 equity 研报任务的状态与结果',
  usage: '/reports status <task_id>',
  args: [{ name: 'task_id', description: '任务 ID', required: true }],
  role: 'user',
  category: 'report',
  handler: async (args) =>
    run(async () => {
      const taskId = args.task_id
      if (!taskId) throw new Error('请提供 task_id')
      const data = unwrap<Record<string, unknown>>(
        await api.get(`/reports/equity/${encodeURIComponent(taskId)}`),
      )
      const lines = Object.entries(data || {}).map(([k, v]) => {
        if (typeof v === 'object' && v !== null) return `- **${k}**: \`${JSON.stringify(v).slice(0, 80)}\``
        return `- **${k}**: ${v ?? '—'}`
      })
      return [`### 研报任务状态（${taskId}）`, '', ...lines].join('\n')
    }),
}

/* ----- 分析类（user） ----- */

const factorCategoriesCommand: SlashCommand = {
  name: 'factor categories',
  description: '查看可用的因子分类',
  usage: '/factor categories',
  args: [],
  role: 'user',
  category: 'analysis',
  handler: async () =>
    run(async () => {
      const items = unwrap<Array<{ value?: string; label?: string; description?: string }>>(
        await api.get('/factor-mining/factor-categories'),
      )
      if (!Array.isArray(items) || !items.length) return '_(暂无因子分类)_'
      const rows = items.map((it) => ({
        value: it.value ?? '—',
        label: it.label ?? '—',
        description: (it.description ?? '').slice(0, 50),
      }))
      return `### 因子分类\n\n${renderTable(rows, [
        { key: 'value', label: '标识' },
        { key: 'label', label: '名称' },
        { key: 'description', label: '说明' },
      ])}`
    }),
}

const backtestStrategiesCommand: SlashCommand = {
  name: 'backtest strategies',
  description: '查看可用的回测策略类型',
  usage: '/backtest strategies',
  args: [],
  role: 'user',
  category: 'analysis',
  handler: async () =>
    run(async () => {
      const data = unwrap<Array<Record<string, unknown>> | Record<string, unknown>>(
        await api.get('/backtesting/strategies'),
      )
      const items = Array.isArray(data) ? data : Object.values(data || {})
      if (!items.length) return '_(暂无策略)_'
      const rows = items.map((s) => ({
        name: String((s as Record<string, unknown>).name ?? (s as Record<string, unknown>).key ?? '—'),
        description: String((s as Record<string, unknown>).description ?? '—').slice(0, 50),
      }))
      return `### 可用回测策略\n\n${renderTable(rows, [
        { key: 'name', label: '策略' },
        { key: 'description', label: '说明' },
      ])}`
    }),
}

/* ----- 管理员：系统类 ----- */

const adminStatusCommand: SlashCommand = {
  name: 'admin status',
  description: '查看平台总览统计（用户/文档/会话/查询/研报）',
  usage: '/admin status',
  args: [],
  role: 'admin',
  category: 'system',
  handler: async () =>
    run(async () => {
      const data = unwrap<Record<string, unknown>>(await adminApi.get('/admin/dashboard'))
      const lines = Object.entries(data || {}).map(([k, v]) => `- **${k}**: ${v ?? '—'}`)
      return [`### 平台总览`, '', ...lines].join('\n')
    }),
}

const adminHealthCommand: SlashCommand = {
  name: 'admin health',
  description: '后端健康检查',
  usage: '/admin health',
  args: [],
  role: 'admin',
  category: 'system',
  handler: async () =>
    run(async () => {
      const data = unwrap<Record<string, unknown>>(await adminApi.get('/admin/health'))
      const lines = Object.entries(data || {}).map(([k, v]) => `- **${k}**: ${v ?? '—'}`)
      return [`### 后端健康状态`, '', ...lines].join('\n')
    }),
}

const usersListCommand: SlashCommand = {
  name: 'users list',
  description: '查看用户列表（仅管理员）',
  usage: '/users list',
  args: [],
  role: 'admin',
  category: 'admin',
  handler: async () =>
    run(async () => {
      const data = unwrap<{ items?: Array<Record<string, unknown>>; total?: number }>(
        await adminApi.get('/users', { params: { page: 1, page_size: 20 } }),
      )
      const items = data?.items || []
      if (!items.length) return '_(暂无用户)_'
      const rows = items.slice(0, 20).map((u) => ({
        id: String(u.id ?? '—'),
        username: String(u.username ?? '—'),
        email: String(u.email ?? '—'),
        role: String(u.role ?? '—'),
        active: u.is_active === true || u.is_active === 'Y' ? '✓' : '—',
      }))
      return `### 用户列表（共 ${data?.total ?? items.length} 个）\n\n${renderTable(rows, [
        { key: 'id', label: 'ID' },
        { key: 'username', label: '用户名' },
        { key: 'email', label: '邮箱' },
        { key: 'role', label: '角色' },
        { key: 'active', label: '启用' },
      ])}`
    }),
}

const auditLogsCommand: SlashCommand = {
  name: 'audit logs',
  description: '查看最近的审计日志（仅管理员）',
  usage: '/audit logs',
  args: [],
  role: 'admin',
  category: 'admin',
  handler: async () =>
    run(async () => {
      const data = unwrap<{ items?: Array<Record<string, unknown>>; total?: number }>(
        await adminApi.get('/audit/logs', { params: { page: 1, page_size: 10 } }),
      )
      const items = data?.items || []
      if (!items.length) return '_(暂无审计日志)_'
      const rows = items.slice(0, 10).map((l) => ({
        time: l.created_at ? new Date(String(l.created_at)).toLocaleString('zh-CN') : '—',
        action: String(l.action ?? '—').slice(0, 30),
        user: String(l.user_id ?? l.username ?? '—'),
        target: String(l.target_type ?? l.resource ?? '—').slice(0, 20),
      }))
      return `### 审计日志（共 ${data?.total ?? items.length} 条）\n\n${renderTable(rows, [
        { key: 'time', label: '时间' },
        { key: 'action', label: '动作' },
        { key: 'user', label: '操作者' },
        { key: 'target', label: '对象' },
      ])}`
    }),
}

const approvalsListCommand: SlashCommand = {
  name: 'approvals list',
  description: '查看待审批报告列表（仅管理员）',
  usage: '/approvals list',
  args: [],
  role: 'admin',
  category: 'admin',
  handler: async () =>
    run(async () => {
      const data = unwrap<{ items?: Array<Record<string, unknown>>; total?: number }>(
        await adminApi.get('/approvals'),
      )
      const items = data?.items || []
      if (!items.length) return '_(暂无审批任务)_'
      const rows = items.slice(0, 15).map((a) => ({
        id: String(a.id ?? a.report_id ?? '—').slice(0, 8),
        title: String(a.title ?? a.report_title ?? '—').slice(0, 30),
        status: String(a.status ?? '—'),
        submitted_by: String(a.submitted_by ?? a.user_id ?? '—'),
      }))
      return `### 审批列表（共 ${data?.total ?? items.length} 条）\n\n${renderTable(rows, [
        { key: 'id', label: 'ID' },
        { key: 'title', label: '标题' },
        { key: 'status', label: '状态' },
        { key: 'submitted_by', label: '提交者' },
      ])}`
    }),
}

const modelsListCommand: SlashCommand = {
  name: 'models list',
  description: '查看 LLM 供应商列表（仅管理员）',
  usage: '/models list',
  args: [],
  role: 'admin',
  category: 'system',
  handler: async () =>
    run(async () => {
      const data = unwrap<{ items?: Array<Record<string, unknown>>; total?: number }>(
        await adminApi.get('/llm-providers', { params: { page: 1, page_size: 20 } }),
      )
      const items = data?.items || []
      if (!items.length) return '_(暂无 LLM 供应商，请先在「LLM 供应商」页面配置)_'
      const rows = items.map((p) => ({
        id: String(p.id ?? '—'),
        name: String(p.name ?? '—'),
        type: String(p.provider_type ?? '—'),
        base_url: String(p.base_url ?? '—').slice(0, 30),
        default: p.is_default ? '✓' : '—',
        active: p.is_active ? '✓' : '—',
        has_key: p.has_api_key ? '✓' : '—',
      }))
      return `### LLM 供应商（共 ${data?.total ?? items.length} 个）\n\n${renderTable(rows, [
        { key: 'id', label: 'ID' },
        { key: 'name', label: '名称' },
        { key: 'type', label: '类型' },
        { key: 'base_url', label: 'Base URL' },
        { key: 'default', label: '默认' },
        { key: 'active', label: '启用' },
        { key: 'has_key', label: '密钥' },
      ])}`
    }),
}

const modelsTestCommand: SlashCommand = {
  name: 'models test',
  description: '测试 LLM 供应商连通性（仅管理员）',
  usage: '/models test <provider_id>',
  args: [{ name: 'provider_id', description: '供应商 ID', required: true }],
  role: 'admin',
  category: 'system',
  handler: async (args) =>
    run(async () => {
      const id = args.provider_id
      if (!id) throw new Error('请提供 provider_id')
      const data = unwrap<{ ok?: boolean; message?: string; latency_ms?: number; tested_at?: string }>(
        await adminApi.post(`/llm-providers/${encodeURIComponent(id)}/test`),
      )
      const icon = data.ok ? '✅' : '❌'
      return [
        `### ${icon} 供应商 #${id} 连通性测试`,
        '',
        `- **结果**: ${data.ok ? '成功' : '失败'}`,
        `- **消息**: ${data.message ?? '—'}`,
        `- **延迟**: ${data.latency_ms != null ? `${data.latency_ms}ms` : '—'}`,
        `- **测试时间**: ${data.tested_at ?? '—'}`,
      ].join('\n')
    }),
}

const templatesListCommand: SlashCommand = {
  name: 'templates list',
  description: '查看研报模板列表',
  usage: '/templates list',
  args: [],
  role: 'admin',
  category: 'report',
  handler: async () =>
    run(async () => {
      const data = unwrap<{ items?: Array<Record<string, unknown>>; total?: number }>(
        await adminApi.get('/report-templates', { params: { page: 1, page_size: 20 } }),
      )
      const items = data?.items || []
      if (!items.length) return '_(暂无模板)_'
      const rows = items.slice(0, 15).map((t) => ({
        id: String(t.id ?? '—').slice(0, 8),
        name: String(t.name ?? '—').slice(0, 30),
        type: String(t.report_type ?? '—'),
        active: t.is_active === 'Y' || t.is_active === true ? '✓' : '—',
      }))
      return `### 研报模板（共 ${data?.total ?? items.length} 个）\n\n${renderTable(rows, [
        { key: 'id', label: 'ID' },
        { key: 'name', label: '名称' },
        { key: 'type', label: '类型' },
        { key: 'active', label: '启用' },
      ])}`
    }),
}

const subscriptionsListCommand: SlashCommand = {
  name: 'subscriptions list',
  description: '查看报告订阅列表',
  usage: '/subscriptions list',
  args: [],
  role: 'admin',
  category: 'report',
  handler: async () =>
    run(async () => {
      const data = unwrap<{ items?: Array<Record<string, unknown>>; total?: number }>(
        await adminApi.get('/report-subscriptions'),
      )
      const items = data?.items || []
      if (!items.length) return '_(暂无订阅)_'
      const rows = items.slice(0, 15).map((s) => ({
        id: String(s.id ?? '—').slice(0, 8),
        name: String(s.name ?? '—').slice(0, 30),
        report_type: String(s.report_type ?? '—'),
        frequency: String(s.frequency ?? s.cron ?? '—'),
        active: s.is_active === true || s.is_active === 'Y' ? '✓' : '—',
      }))
      return `### 报告订阅（共 ${data?.total ?? items.length} 个）\n\n${renderTable(rows, [
        { key: 'id', label: 'ID' },
        { key: 'name', label: '名称' },
        { key: 'report_type', label: '类型' },
        { key: 'frequency', label: '频率' },
        { key: 'active', label: '启用' },
      ])}`
    }),
}

/* ------------------------------------------------------------------ */
/*  命令注册表                                                         */
/* ------------------------------------------------------------------ */

export const SLASH_COMMANDS: SlashCommand[] = [
  helpCommand,
  dashboardCommand,
  queriesHistoryCommand,
  conversationsListCommand,
  documentsListCommand,
  reportsListCommand,
  reportsGenerateCommand,
  reportsStatusCommand,
  factorCategoriesCommand,
  backtestStrategiesCommand,
  // admin only
  adminStatusCommand,
  adminHealthCommand,
  usersListCommand,
  auditLogsCommand,
  approvalsListCommand,
  modelsListCommand,
  modelsTestCommand,
  templatesListCommand,
  subscriptionsListCommand,
]

/** 按角色过滤可用命令 */
export function getCommandsForRole(role: string | null): SlashCommand[] {
  if (role === 'admin') return SLASH_COMMANDS
  return SLASH_COMMANDS.filter((c) => c.role === 'user')
}

/* ------------------------------------------------------------------ */
/*  解析与执行                                                         */
/* ------------------------------------------------------------------ */

export interface ParsedCommand {
  command: SlashCommand
  args: Record<string, string>
  /** 原始输入（用于回显） */
  raw: string
}

/**
 * 解析斜杠命令。返回 null 表示不是斜杠命令（按普通对话处理）。
 *
 * 输入示例：
 *   "/help" -> { command: helpCommand, args: {} }
 *   "/models list" -> { command: modelsListCommand, args: {} }
 *   "/models test 5" -> { command: modelsTestCommand, args: { provider_id: "5" } }
 *   "/reports generate 600519 贵州茅台" -> { command: reportsGenerateCommand, args: { ticker: "600519", company: "贵州茅台" } }
 */
export function parseSlashCommand(
  input: string,
  role: string | null,
): ParsedCommand | null {
  const trimmed = input.trim()
  if (!trimmed.startsWith('/')) return null

  // 去掉前导 /
  const body = trimmed.slice(1).trim()
  // 按空白分割，但保留后续参数为整体（用于带空格的值如公司名）
  const parts = body.split(/\s+/)
  if (!parts.length) return null

  const available = getCommandsForRole(role)

  // 优先匹配多词命令名（如 "models list"），再退到单词
  for (let i = Math.min(parts.length, 3); i >= 1; i--) {
    const cmdName = parts.slice(0, i).join(' ').toLowerCase()
    const cmd = available.find((c) => c.name.toLowerCase() === cmdName)
    if (cmd) {
      const argValues = parts.slice(i)
      const args: Record<string, string> = {}
      cmd.args.forEach((arg, idx) => {
        if (idx === cmd.args.length - 1 && argValues.length > idx) {
          // 最后一个参数吃掉剩余所有值（支持带空格的值）
          args[arg.name] = argValues.slice(idx).join(' ')
        } else {
          args[arg.name] = argValues[idx] ?? arg.default ?? ''
        }
      })
      return { command: cmd, args, raw: trimmed }
    }
  }

  // 没匹配上 — 如果是 admin 但用了 admin-only 命令，给出明确提示
  const allCmds = SLASH_COMMANDS
  for (let i = Math.min(parts.length, 3); i >= 1; i--) {
    const cmdName = parts.slice(0, i).join(' ').toLowerCase()
    const cmd = allCmds.find((c) => c.name.toLowerCase() === cmdName)
    if (cmd && cmd.role === 'admin' && role !== 'admin') {
      throw new Error(
        `命令 "/${cmd.name}" 仅管理员可用 — 当前角色为 ${role || '未知'}，无法执行此操作`,
      )
    }
    if (cmd) {
      throw new Error(`命令 "/${cmd.name}" 存在但当前角色不可用`)
    }
  }

  throw new Error(
    `未知命令: "${parts.join(' ')}" — 输入 /help 查看可用命令列表`,
  )
}

/** 生成 help 命令的 Markdown 输出（按角色过滤） */
export function renderHelpForRole(role: string | null): string {
  const cmds = getCommandsForRole(role)
  const groups: Record<CommandCategory, SlashCommand[]> = {
    help: [],
    data: [],
    report: [],
    analysis: [],
    admin: [],
    system: [],
  }
  cmds.forEach((c) => groups[c.category].push(c))

  const categoryLabels: Record<CommandCategory, string> = {
    help: '帮助',
    data: '数据查询',
    report: '研报',
    analysis: '分析工具',
    admin: '管理（仅管理员）',
    system: '系统',
  }

  const sections: string[] = ['### 可用斜杠命令', '']
  Object.entries(groups).forEach(([cat, items]) => {
    if (!items.length) return
    sections.push(`#### ${categoryLabels[cat as CommandCategory]}`)
    sections.push('')
    items.forEach((c) => {
      sections.push(`- \`/${c.usage}\` — ${c.description}`)
    })
    sections.push('')
  })

  sections.push('_提示：在输入框输入 `/` 会自动弹出命令面板_')

  return sections.join('\n')
}
