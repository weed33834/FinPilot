import { describe, it, expect } from 'vitest'
import {
  getMobileNav,
  isMobileSupportedPath,
  MOBILE_PRIMARY_PATHS,
} from '../components/mobile/mobileNav'

describe('移动端导航派生', () => {
  it('底部 Tab 固定为 4 个主入口', () => {
    const nav = getMobileNav('admin')
    expect(nav.primary.map((p) => p.path)).toEqual(MOBILE_PRIMARY_PATHS)
  })

  it('「更多」分组剔除主入口路径', () => {
    const nav = getMobileNav('admin')
    const morePaths = nav.moreSections.flatMap((s) => s.items.map((i) => i.path))
    MOBILE_PRIMARY_PATHS.forEach((p) => expect(morePaths).not.toContain(p))
  })

  it('按角色过滤可见项（admin 可见审批，匿名不可见）', () => {
    const adminPaths = getMobileNav('admin').moreSections.flatMap((s) =>
      s.items.map((i) => i.path),
    )
    const anonPaths = getMobileNav(undefined).moreSections.flatMap((s) =>
      s.items.map((i) => i.path),
    )
    expect(adminPaths).toContain('/approvals')
    expect(anonPaths).not.toContain('/approvals')
  })
})

describe('isMobileSupportedPath', () => {
  it('命中已做移动端独立设计的页面（含子路由）', () => {
    expect(isMobileSupportedPath('/documents')).toBe(true)
    expect(isMobileSupportedPath('/documents/123')).toBe(true)
    expect(isMobileSupportedPath('/reports/abc')).toBe(true)
    expect(isMobileSupportedPath('/security')).toBe(true)
  })

  it('未独立设计的页面走降级提示', () => {
    expect(isMobileSupportedPath('/users')).toBe(false)
    expect(isMobileSupportedPath('/admin')).toBe(false)
    expect(isMobileSupportedPath('/conversations')).toBe(false)
    expect(isMobileSupportedPath('/kpi')).toBe(false)
  })
})
