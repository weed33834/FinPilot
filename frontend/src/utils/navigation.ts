/**
 * FinPilot 主导航配置 — 多级折叠菜单
 *
 * 设计原则：
 * 1. 以对话为中心：智能对话放在第一位、设为默认入口
 * 2. 多级分组：5 大组 + 子菜单可展开
 * 3. 角色驱动：每个菜单项声明所需角色
 * 4. 平铺管理：取消旧的"主侧栏 + admin 侧栏"双重布局
 *
 * 由 Sidebar 组件消费此配置生成菜单。
 */

import type { RoleKey } from './permissions'
import type { IconName } from '../components/ui/Icons'

export interface NavItem {
  path: string
  labelKey: string
  icon: IconName
  /** 默认展开的子菜单（无子项时为 undefined） */
  children?: NavItem[]
  /** 见此菜单项所需的角色（任一即可）；不填表示所有登录用户可见 */
  roles?: RoleKey[]
  /** 标记为默认入口（用于品牌点击跳转） */
  isHome?: boolean
  /** 标记为新功能徽章 */
  badge?: 'new' | 'beta'
}

export interface NavSection {
  titleKey: string
  items: NavItem[]
}

// 便捷别名
const ADMIN: RoleKey[] = ['admin']
const APPROVERS: RoleKey[] = ['admin', 'auditor']
const FINANCE_MGR: RoleKey[] = ['admin', 'finance_manager']
const RESEARCHERS: RoleKey[] = ['admin', 'finance_manager', 'researcher']
const MONITORS: RoleKey[] = ['admin', 'auditor']

export const NAV_SECTIONS: NavSection[] = [
  // ============================================================
  // 1. 工作台 — 对话驱动入口
  // ============================================================
  {
    titleKey: 'menu:groups.workspace',
    items: [
      {
        path: '/agent',
        labelKey: 'menu:items.agent',
        icon: 'agent',
        isHome: true,
      },
      {
        path: '/conversations',
        labelKey: 'menu:items.conversations',
        icon: 'copy',
      },
      {
        path: '/dashboard',
        labelKey: 'menu:items.dashboard',
        icon: 'dashboard',
      },
      {
        path: '/kpi',
        labelKey: 'menu:items.kpi',
        icon: 'trend',
      },
      {
        path: '/queries',
        labelKey: 'menu:items.queries',
        icon: 'queries',
      },
    ],
  },

  // ============================================================
  // 2. 财务
  // ============================================================
  {
    titleKey: 'menu:groups.finance',
    items: [
      {
        path: '/reports',
        labelKey: 'menu:items.reports',
        icon: 'reports',
      },
      {
        path: '/report-templates',
        labelKey: 'menu:items.reportTemplates',
        icon: 'templates',
        roles: FINANCE_MGR,
      },
      {
        path: '/report-subscriptions',
        labelKey: 'menu:items.reportSubscriptions',
        icon: 'subscriptions',
        roles: FINANCE_MGR,
      },
    ],
  },

  // ============================================================
  // 3. 文档与审批
  // ============================================================
  {
    titleKey: 'menu:groups.docsApproval',
    items: [
      {
        path: '/documents',
        labelKey: 'menu:items.documents',
        icon: 'documents',
      },
      {
        path: '/approvals',
        labelKey: 'menu:items.approvals',
        icon: 'approvals',
        roles: APPROVERS,
      },
      {
        path: '/hitl',
        labelKey: 'menu:items.hitl',
        icon: 'audit',
        roles: APPROVERS,
      },
      {
        path: '/reflections',
        labelKey: 'menu:items.reflections',
        icon: 'reflections',
        roles: APPROVERS,
      },
    ],
  },

  // ============================================================
  // 4. 审计与监控
  // ============================================================
  {
    titleKey: 'menu:groups.audit',
    items: [
      {
        path: '/security',
        labelKey: 'menu:items.security',
        icon: 'security',
      },
      {
        path: '/audit',
        labelKey: 'menu:items.audit',
        icon: 'audit',
      },
      {
        path: '/admin/runtime-logs',
        labelKey: 'menu:items.runtimeLogs',
        icon: 'audit',
        roles: MONITORS,
      },
      {
        path: '/admin/eval-management',
        labelKey: 'menu:items.evalManagement',
        icon: 'queries',
        roles: MONITORS,
      },
    ],
  },

  // ============================================================
  // 5. 管理 — 仅 admin 可见的整组，含子菜单展开
  // ============================================================
  {
    titleKey: 'menu:groups.management',
    items: [
      // 用户与权限
      {
        path: '/admin/users-group',
        labelKey: 'menu:items.userPermissions',
        icon: 'users',
        roles: ADMIN,
        children: [
          { path: '/users', labelKey: 'menu:items.users', icon: 'users' },
          { path: '/access-policies', labelKey: 'menu:items.accessPolicies', icon: 'policies' },
          { path: '/api-keys', labelKey: 'menu:items.apiKeys', icon: 'apiKeys' },
        ],
      },
      // AI 资源
      {
        path: '/admin/ai-resources',
        labelKey: 'menu:items.aiResources',
        icon: 'llm',
        roles: ADMIN,
        children: [
          { path: '/llm-providers', labelKey: 'menu:items.llmProviders', icon: 'llm' },
          { path: '/admin/models', labelKey: 'menu:items.modelConfigs', icon: 'llm' },
          { path: '/admin/prompts', labelKey: 'menu:items.prompts', icon: 'documents' },
          { path: '/admin/prompt-deep', labelKey: 'menu:items.promptDeep', icon: 'copy' },
          { path: '/admin/skills', labelKey: 'menu:items.skills', icon: 'templates' },
          { path: '/admin/agents', labelKey: 'menu:items.agents', icon: 'agent' },
        ],
      },
      // 工具与扩展
      {
        path: '/admin/tools-group',
        labelKey: 'menu:items.toolsExtensions',
        icon: 'apiKeys',
        roles: ADMIN,
        children: [
          { path: '/admin/tools', labelKey: 'menu:items.tools', icon: 'queries' },
          { path: '/admin/tool-monitoring', labelKey: 'menu:items.toolMonitoring', icon: 'audit' },
          { path: '/admin/mcp-servers', labelKey: 'menu:items.mcpServers', icon: 'apiKeys' },
          { path: '/admin/search-engines', labelKey: 'menu:items.searchEngines', icon: 'search' },
          { path: '/admin/sandbox-configs', labelKey: 'menu:items.sandboxConfigs', icon: 'security' },
          { path: '/admin/context-management', labelKey: 'menu:items.contextManagement', icon: 'templates' },
        ],
      },
      // 量化研究
      {
        path: '/admin/research',
        labelKey: 'menu:items.research',
        icon: 'trend',
        roles: RESEARCHERS,
        children: [
          { path: '/admin/factor-mining', labelKey: 'menu:items.factorMining', icon: 'trend' },
          { path: '/admin/backtesting', labelKey: 'menu:items.backtesting', icon: 'refresh' },
          { path: '/admin/workflow-editor', labelKey: 'menu:items.workflowEditor', icon: 'templates' },
        ],
      },
      // 系统
      {
        path: '/admin/system',
        labelKey: 'menu:items.system',
        icon: 'settings',
        roles: ADMIN,
        children: [
          { path: '/admin', labelKey: 'menu:items.adminOverview', icon: 'dashboard' },
          { path: '/admin/settings', labelKey: 'menu:items.settings', icon: 'settings' },
        ],
      },
    ],
  },
]

/** 默认展开的子菜单路径前缀（命中即展开） */
export function shouldExpandGroup(currentPath: string, groupPath: string): boolean {
  return currentPath === groupPath || currentPath.startsWith(groupPath + '/')
}

/** 根据角色过滤可见的导航项 */
export function filterNavByRole(
  sections: NavSection[],
  role: string | null | undefined
): NavSection[] {
  const filterItem = (item: NavItem): NavItem | null => {
    if (item.roles && item.roles.length > 0) {
      // admin 永远可见；其他角色需在白名单
      if (role !== 'admin' && !item.roles.includes(role as RoleKey)) {
        return null
      }
    }
    if (item.children) {
      const kids = item.children
        .map(filterItem)
        .filter((k): k is NavItem => k !== null)
      if (kids.length === 0) return null
      return { ...item, children: kids }
    }
    return item
  }

  return sections
    .map((section) => ({
      ...section,
      items: section.items
        .map(filterItem)
        .filter((item): item is NavItem => item !== null),
    }))
    .filter((section) => section.items.length > 0)
}


