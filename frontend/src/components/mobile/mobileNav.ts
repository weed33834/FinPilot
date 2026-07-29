import {
  NAV_SECTIONS,
  filterNavByRole,
  type NavItem,
  type NavSection,
} from '../../utils/navigation'

/** 移动端底部 Tab 固定主目的（按角色过滤后可见者才展示）。 */
export const MOBILE_PRIMARY_PATHS = ['/agent', '/dashboard', '/documents', '/reports']

/**
 * 已做移动端独立设计的页面路径（含子路由）。
 * 其余路由在移动端统一走「建议在桌面端使用」降级提示，不为后台/配置类页面单独重设计。
 */
export const MOBILE_SUPPORTED_PATHS = [
  '/agent',
  '/dashboard',
  '/documents',
  '/reports',
  '/approvals',
  '/hitl',
  '/security',
]

/** 判断某路径是否已有移动端独立设计（命中前缀即视为支持）。 */
export function isMobileSupportedPath(pathname: string): boolean {
  return MOBILE_SUPPORTED_PATHS.some(
    (p) => pathname === p || pathname.startsWith(p + '/'),
  )
}

/** 把多级导航拍平为叶子节点列表（跳过带 children 的组父节点）。 */
export function flattenLeaves(sections: NavSection[]): NavItem[] {
  const out: NavItem[] = []
  const walk = (items: NavItem[]) => {
    for (const it of items) {
      if (it.children && it.children.length > 0) walk(it.children)
      else out.push(it)
    }
  }
  sections.forEach((s) => walk(s.items))
  return out
}

export interface MobileNav {
  /** 底部 Tab 主目的（已按角色过滤、按 MOBILE_PRIMARY_PATHS 排序） */
  primary: NavItem[]
  /** “更多”弹层里的分组次级目的 */
  moreSections: NavSection[]
}

/**
 * 由统一导航数据源 NAV_SECTIONS 派生移动端导航：
 * - primary：4 个高频入口（对话/仪表盘/文档/报告），构成底部 Tab。
 * - moreSections：其余全部目的，按原分组在“更多”底部弹层里列出。
 * 全部经过角色过滤，管理员可见项更多。
 */
export function getMobileNav(role: string | null | undefined): MobileNav {
  const sections = filterNavByRole(NAV_SECTIONS, role)
  const leaves = flattenLeaves(sections)

  const primary = MOBILE_PRIMARY_PATHS.map((p) =>
    leaves.find((l) => l.path === p)
  ).filter((x): x is NavItem => Boolean(x))

  const primarySet = new Set(primary.map((p) => p.path))
  const moreSections = sections
    .map((s) => ({
      ...s,
      items: s.items
        .flatMap((it) => (it.children && it.children.length > 0 ? it.children : [it]))
        .filter((it) => !primarySet.has(it.path)),
    }))
    .filter((s) => s.items.length > 0)

  return { primary, moreSections }
}

/** 根据当前路径匹配最合适的导航项（用于顶栏标题），取最长前缀匹配。 */
export function matchNavItem(
  leaves: NavItem[],
  pathname: string
): NavItem | undefined {
  return leaves
    .filter(
      (it) => pathname === it.path || pathname.startsWith(it.path + '/')
    )
    .sort((a, b) => b.path.length - a.path.length)[0]
}
