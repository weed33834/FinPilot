// 端到端复现脚本：驱动真实运行的 FinPilot 前端（http://localhost:5174），
// 登录后依次点击侧边栏各菜单，检查「URL 变化」与「页面主标题(内容)变化」是否同步。
// 使用本机 Edge（Chromium 内核）作为浏览器，免去下载 chromium。
import { chromium } from 'playwright'
import fs from 'node:fs'
import path from 'node:path'

const FRONTEND = 'http://localhost:5174'
const EDGE = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'

function loadEnv() {
  const envPath = path.resolve(process.cwd(), '..', '.env')
  const text = fs.readFileSync(envPath, 'utf8')
  const out = {}
  // 兼容 Windows CRLF：按 \r?\n 切分并 trim，否则行尾 \r 会让 ^KEY=(.*)$ 匹配失败。
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim()
    const m = line.match(/^([A-Z0-9_]+)=(.*)$/)
    if (m) out[m[1]] = m[2].trim()
  }
  return out
}
const env = loadEnv()
const EMAIL = env.FINPILOT_ADMIN_EMAIL || 'admin@finpilot.ai'
const PASS = env.FINPILOT_ADMIN_PASSWORD

const consoleErrors = []
const pageErrors = []
const unauthorizedUrls = []

async function mainH1(page) {
  const el = page.locator('main h1').first()
  try {
    return (await el.innerText()).trim()
  } catch {
    return null
  }
}

const targets = [
  '/agent',
  '/documents',
  '/reports',
  '/queries',
  '/conversations',
  '/kpi',
  '/audit',
  '/security',
  '/admin/models',
]

try {
  const browser = await chromium.launch({
    executablePath: EDGE,
    headless: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  })
  const context = await browser.newContext()
  const page = await context.newPage()
  page.on('console', (m) => {
    if (m.type() === 'error') consoleErrors.push(m.text())
  })
  page.on('pageerror', (e) => pageErrors.push(e.message))
  page.on('response', (r) => {
    if (r.status() === 401) unauthorizedUrls.push(r.url())
  })

  console.log('=== 登录 ===')
  await page.goto(`${FRONTEND}/login`, { waitUntil: 'domcontentloaded', timeout: 20000 })
  await page.fill('#username', EMAIL)
  await page.fill('#password', PASS)
  await page.click('button[type="submit"]')
  // 等待进入应用外壳（侧边栏链接出现），避免停留在登录/过渡态导致找不到链接。
  await page.waitForSelector('a.sidebar-link', { timeout: 20000 })
  await page.waitForURL('**/dashboard', { timeout: 20000 })
  await page.waitForSelector('main h1', { timeout: 20000 })
  console.log('已登录，当前 URL =', page.url())

  // 点击侧边栏链接前，若其位于折叠分组内（child link 不可见），先展开父分组头。
  // 否则 collapsed 的 child link 为 display:none，Playwright 无法点击 => 误报失败。
  async function clickSidebarLink(target) {
    const link = page
      .locator(`a.sidebar-link[href="${target}"], a.sidebar-link-child[href="${target}"]`)
      .first()
    if ((await link.count()) === 0) return false
    const visible = await link.isVisible().catch(() => false)
    if (!visible) {
      const group = link.locator('xpath=ancestor::div[contains(@class,"sidebar-nav-group")]').first()
      const header = group.locator('.sidebar-nav-group-header').first()
      if ((await header.count()) > 0) {
        await header.click()
        await page.waitForTimeout(350)
      }
    }
    // 确保链接可见后再点击（折叠态可能仍有瞬时隐藏）
    await link.waitFor({ state: 'visible', timeout: 5000 }).catch(() => {})
    await link.click({ force: true })
    return true
  }

  // 预热：依次访问各路由一次以缓存懒加载 chunk。避免断言阶段因「首次冷加载」超过等待
  // 超时而被误判为导航失效——这与导航逻辑无关，纯属资源加载耗时。
  console.log('=== 预热（缓存懒加载 chunk）===')
  for (const target of targets) {
    const ok = await clickSidebarLink(target)
    if (ok) await page.waitForTimeout(600)
  }
  // 回到 dashboard 作为断言起点
  await clickSidebarLink('/dashboard')
  await page.waitForTimeout(600)

  const results = []
  for (const target of targets) {
    const urlBefore = page.url()
    const h1Before = await mainH1(page)
    const found = await clickSidebarLink(target)
    if (!found) {
      results.push({ target, ok: false, reason: '侧边栏未找到该链接', urlAfter: urlBefore, h1After: h1Before })
      continue
    }
    let urlChanged = false
    try {
      await page.waitForURL(`**${target}`, { timeout: 12000 })
      urlChanged = true
    } catch {
      urlChanged = false
    }
    const urlAfter = page.url()
    let contentChanged = false
    let h1After = h1Before
    try {
      await page.waitForFunction(
        (prev) => {
          const el = document.querySelector('main h1')
          const t = el ? el.textContent.trim() : null
          return t !== null && t !== prev
        },
        h1Before,
        { timeout: 15000 },
      )
      contentChanged = true
      h1After = await mainH1(page)
    } catch {
      contentChanged = false
      h1After = await mainH1(page)
    }
    const ok = urlChanged && contentChanged
    results.push({ target, ok, urlBefore, urlAfter, h1Before, h1After, urlChanged, contentChanged })
  }

  console.log('\n=== 导航测试结果 ===')
  for (const r of results) {
    if (r.ok) {
      console.log(`✅ ${r.target}  URL: ${r.urlBefore} -> ${r.urlAfter}  内容: "${r.h1Before}" -> "${r.h1After}"`)
    } else {
      console.log(
        `❌ ${r.target}  URL变化=${r.urlChanged} 内容变化=${r.contentChanged}  当前URL=${r.urlAfter}  h1="${r.h1After}"  ${r.reason || ''}`,
      )
    }
  }

  console.log('\n=== 控制台错误 (前10) ===')
  consoleErrors.slice(0, 10).forEach((e) => console.log('  [console.error]', e))
  console.log('=== 页面异常 (前10) ===')
  pageErrors.slice(0, 10).forEach((e) => console.log('  [pageerror]', e))
  console.log('=== 401 未授权接口 (去重, 前10) ===')
  ;[...new Set(unauthorizedUrls)].slice(0, 10).forEach((u) => console.log('  [401]', u))

  await browser.close()

  const failed = results.filter((r) => !r.ok)
  console.log(`\n汇总: ${results.length - failed.length}/${results.length} 通过`)
  if (failed.length) process.exit(2)
} catch (e) {
  console.error('脚本执行出错:', e)
  process.exit(1)
}
