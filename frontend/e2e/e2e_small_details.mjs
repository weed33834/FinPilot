// 小细节全面检查 — 登录边界、表单验证、导航状态、空态文案、键盘操作等

import { chromium } from 'playwright';
import { readFileSync } from 'fs';

const BASE = 'http://localhost:5174';
let PASS = 0, FAIL = 0;
function ok(label, yes, detail='') {
  if (yes) { PASS++; console.log('✅ ' + label + (detail ? ' | ' + detail : '')); }
  else { FAIL++; console.log('❌ ' + label + (detail ? ' | ' + detail : '')); }
}

async function main() {
  console.log('╔══════════════════════════════════════╗');
  console.log('║  小细节边缘情况全面检查              ║');
  console.log('╚══════════════════════════════════════╝\n');

  const browser = await chromium.launch({
    executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true,
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [];
  page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()) });
  page.on('pageerror', e => errors.push('JS: ' + e.message));

  // ====== 1. 登录页细节 ======
  console.log('\n=== 1. 登录页细节 ===');
  await page.goto(BASE + '/login', { waitUntil: 'domcontentloaded', timeout: 15000 });
  await page.waitForTimeout(1000);

  // 1a. 空提交 — 验证按钮是否disabled
  await page.fill('input[name="username"]', '');
  await page.fill('input[name="password"]', '');
  const btnDisabled = await page.evaluate(() => {
    const btn = document.querySelector('button[type="submit"]');
    return btn?.disabled || btn?.getAttribute('disabled') !== null;
  });
  ok('空表单按钮禁用', btnDisabled, '符合预期');

  // 1b. 错误密码 — 按钮应启用，点击后应有错误提示
  await page.fill('input[name="username"]', 'admin@finpilot.ai');
  await page.fill('input[name="password"]', 'wrongpassword');
  await page.waitForTimeout(300);
  // 用 evaluate 点击（绕过 Playwright 的 enabled 检查）
  await page.evaluate(() => {
    const btn = document.querySelector('button[type="submit"]');
    if (btn && !btn.disabled) btn.click();
  });
  await page.waitForTimeout(3000);
  const wrongPwd = await page.evaluate(() => {
    return document.body.innerText.includes('错误') || document.body.innerText.includes('失败') || 
           document.body.innerText.includes('无效') || document.body.innerText.includes('invalid') ||
           document.body.innerText.includes('Incorrect') || document.body.innerText.includes('Error');
  });
  ok('错误密码提示', wrongPwd, '有错误反馈');

  // 1c. Tab顺序
  await page.fill('input[name="username"]', '');
  await page.keyboard.press('Tab');
  const tabFocus = await page.evaluate(() => document.activeElement?.getAttribute('name') || document.activeElement?.tagName || '');
  ok('Tab键跳转', tabFocus === 'password' || tabFocus === 'INPUT', '焦点=' + tabFocus);

  // ====== 2. 登录成功 ======
  console.log('\n=== 2. 登录成功 ===');
  await page.fill('input[name="username"]', 'admin@finpilot.ai');
  await page.fill('input[name="password"]', 'w9MIquomakyemjLOzaOChA');
  await page.click('button[type="submit"]');
  await page.waitForURL('**/dashboard', { timeout: 15000 });
  ok('登录跳转工作台', page.url().includes('dashboard'));

  // ====== 3. 侧边导航细节 ======
  console.log('\n=== 3. 侧边导航细节 ===');
  const navItems = await page.evaluate(() => {
    return [...document.querySelectorAll('aside a, [class*="Sidebar"] a, nav a')]
      .filter(a => a.offsetParent)
      .map(a => ({ text: a.textContent?.trim()?.substring(0, 20), href: a.getAttribute('href') || '' }));
  });
  ok('导航链接', navItems.length >= 5, `${navItems.length}个`);
  if (navItems.length > 0) {
    // 点击第三个导航项
    const navLink = page.locator('aside a, [class*="Sidebar"] a, nav a').nth(2);
    if (await navLink.isVisible({ timeout: 2000 }).catch(() => false)) {
      const before = page.url();
      await navLink.click();
      await page.waitForTimeout(2000);
      ok('导航点击跳转', page.url() !== before, page.url().split('/').pop());
    }
  }

  // ====== 4. 各页面空态文案 ======
  console.log('\n=== 4. 空态文案检查 ===');
  const emptyPages = [
    { path: '/api-keys', name: 'API密钥', match: '密钥' },
    { path: '/access-policies', name: '访问策略', match: '策略' },
    { path: '/report-subscriptions', name: '报告订阅', match: '订阅' },
    { path: '/report-templates', name: '报告模板', match: '模板' },
    { path: '/conversations', name: '对话历史', match: '对话|历史|暂无' },
    { path: '/admin/skills', name: '技能管理', match: '技能' },
    { path: '/admin/tools', name: '工具管理', match: '工具' },
    { path: '/admin/search-engines', name: '搜索引擎', match: '搜索|引擎' },
    { path: '/admin/mcp-servers', name: 'MCP', match: 'MCP|服务器' },
    { path: '/admin/agents', name: 'agent配置', match: 'Agent|配置|暂无' },
  ];
  for (const p of emptyPages) {
    await page.goto(BASE + p.path, { waitUntil: 'domcontentloaded', timeout: 15000 });
    await page.waitForTimeout(3000);
    const hasText = await page.evaluate((m) => new RegExp(m).test(document.body.innerText || ''), p.match);
    ok(p.name + '空态', hasText);
  }

  // ====== 5. 表单验证细节 ======
  console.log('\n=== 5. 表单验证 ===');
  // 5a. LLM供应商表单
  await page.goto(BASE + '/llm-providers', { waitUntil: 'domcontentloaded', timeout: 15000 });
  await page.waitForTimeout(3000);
  const createProviderBtn = page.locator('button:has-text("新建")').first();
  if (await createProviderBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
    await createProviderBtn.click();
    await page.waitForTimeout(2000);
    const hasNameInput = await page.locator('input[name="name"], input[placeholder*="名称"]').first().isVisible().catch(() => false);
    ok('LLM供应商表单', hasNameInput, '模态框打开');
  }
  // 5b. API密钥表单
  await page.goto(BASE + '/api-keys', { waitUntil: 'domcontentloaded', timeout: 15000 });
  await page.waitForTimeout(2000);
  const createApiBtn = page.locator('button:has-text("新建")').first();
  if (await createApiBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
    await createApiBtn.click();
    await page.waitForTimeout(1500);
    const modalVis = await page.locator('[class*="modal"], [class*="dialog"]').first().isVisible().catch(() => false);
    ok('API密钥表单', modalVis);
  }

  // ====== 6. 退出登录 ======
  console.log('\n=== 6. 退出登录 ===');
  const logoutBtn = page.locator('button:has-text("退出"), [class*="logout"], [class*="Logout"]').first();
  const hasLogout = await logoutBtn.isVisible({ timeout: 2000 }).catch(() => false);
  ok('退出按钮可见', hasLogout, page.url());

  // ====== 7. Console错误汇总 ======
  console.log('\n=== 7. Console错误 ===');
  const uniqueErrs = [...new Set(errors)].filter(e => !e.includes('/auth/me') && !e.includes('favicon'));
  ok('无功能性错误', uniqueErrs.length === 0, uniqueErrs.length + '条');

  // ====== 8. Toast ======
  console.log('\n=== 8. Toast通知检查 ===');
  await page.goto(BASE + '/documents', { waitUntil: 'domcontentloaded', timeout: 15000 });
  await page.waitForTimeout(3000);
  // Trigger a toast by trying a delete
  const delBtn = page.locator('button:has-text("删除")').first();
  if (await delBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
    await delBtn.click();
    await page.waitForTimeout(1000);
    const confirmBtn = page.locator('button:has-text("确定"), button:has-text("确认")').first();
    const hasConfirm = await confirmBtn.isVisible({ timeout: 2000 }).catch(() => false);
    ok('删除确认弹窗', hasConfirm);
    if (!hasConfirm) {
      // Close modal if opened
      const cancelBtn = page.locator('button:has-text("取消")').first();
      await cancelBtn.click().catch(() => {});
    }
  }

  // ====== 汇总 ======
  console.log('\n========================================');
  console.log(`  小细节检查: ${PASS}✅ / ${FAIL}❌`);
  console.log('========================================');
  if (uniqueErrs.length > 0) {
    console.log('\nConsole errors:');
    uniqueErrs.forEach(e => console.log('  ' + e.substring(0, 150)));
  }
  await browser.close();
}

main().catch(e => { console.error('FATAL:', e.message); process.exit(1); });
