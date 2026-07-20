/**
 * FinPilot 权限模型 — 集中管理角色与可见菜单
 *
 * 4 个内置角色：
 * - admin            全权限
 * - finance_manager  工作台 + 财务 + 报告订阅/模板 + 量化研究
 * - auditor          工作台 + 财务只读 + 文档与审批 + 审计与监控
 * - viewer           工作台只读 + 财务只读
 * - researcher       工作台 + 量化研究（新增）
 *
 * 菜单分组与可见性在此声明，由 Sidebar 与 PrivateRoute 共同消费。
 * 修改权限只需更新这一份配置。
 */

export type RoleKey = 'admin' | 'finance_manager' | 'auditor' | 'viewer' | 'researcher'

export const ALL_ROLES: RoleKey[] = ['admin', 'finance_manager', 'auditor', 'viewer', 'researcher']

export const ROLE_LABELS: Record<RoleKey, string> = {
  admin: '管理员',
  finance_manager: '财务经理',
  auditor: '审计员',
  viewer: '查看者',
  researcher: '研究员',
}

/** 角色中文简介，用于个人中心展示 */
export const ROLE_DESCRIPTIONS: Record<RoleKey, string> = {
  admin: '拥有全部权限，可管理系统配置与所有功能模块',
  finance_manager: '管理财务报告、报告模板与订阅，可使用量化研究工具',
  auditor: '负责报告审批、人工审批与审计监控，可只读访问财务数据',
  viewer: '只读访问工作台与财务数据',
  researcher: '专注量化研究，可使用因子挖掘、策略回测与工作流编辑器',
}

/**
 * 判断角色是否具备某权限。
 * - admin 自动通过所有检查
 * - 其他角色需在 allowed 列表中
 */
export function can(role: string | null | undefined, allowed: RoleKey[]): boolean {
  if (!role) return false
  if (role === 'admin') return true
  return allowed.includes(role as RoleKey)
}

/** 路由级权限白名单（与 PrivateRoute 的 roles 参数对应） */
export const ROUTE_PERMISSIONS = {
  // 工作台 — 所有登录用户
  agent: ALL_ROLES,
  conversations: ALL_ROLES,
  dashboard: ALL_ROLES,
  kpi: ALL_ROLES,
  queries: ALL_ROLES,

  // 财务 — 所有登录用户（viewer 只读由页面内部控制）
  reports: ALL_ROLES,
  'report-templates': ['admin', 'finance_manager'] as RoleKey[],
  'report-subscriptions': ['admin', 'finance_manager'] as RoleKey[],

  // 文档与审批
  documents: ALL_ROLES,
  approvals: ['admin', 'auditor'] as RoleKey[],
  reflections: ['admin', 'auditor'] as RoleKey[],
  hitl: ['admin', 'auditor'] as RoleKey[],

  // 审计与监控
  audit: ALL_ROLES,
  'runtime-logs': ['admin', 'auditor'] as RoleKey[],

  // 个人中心
  security: ALL_ROLES,

  // === 管理面板（admin/* 路径段） ===
  users: ['admin'] as RoleKey[],
  'access-policies': ['admin'] as RoleKey[],
  'api-keys': ['admin'] as RoleKey[],
  'llm-providers': ['admin'] as RoleKey[],
  prompts: ['admin'] as RoleKey[],
  'prompt-deep': ['admin'] as RoleKey[],
  skills: ['admin'] as RoleKey[],
  agents: ['admin'] as RoleKey[],
  tools: ['admin'] as RoleKey[],
  'tool-monitoring': ['admin'] as RoleKey[],
  'mcp-servers': ['admin'] as RoleKey[],
  'search-engines': ['admin'] as RoleKey[],
  'sandbox-configs': ['admin'] as RoleKey[],
  'context-management': ['admin'] as RoleKey[],
  'eval-management': ['admin', 'auditor'] as RoleKey[],
  settings: ['admin'] as RoleKey[],

  // 量化研究 — admin / finance_manager / researcher
  'factor-mining': ['admin', 'finance_manager', 'researcher'] as RoleKey[],
  backtesting: ['admin', 'finance_manager', 'researcher'] as RoleKey[],
  'workflow-editor': ['admin', 'finance_manager', 'researcher'] as RoleKey[],
} as const
