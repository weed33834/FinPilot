// E2E: 模拟真实用户，逐个测试所有用户端功能页面

import { chromium } from 'playwright';
import { readFileSync } from 'fs';

function loadEnv() {
  const text = readFileSync('../.env', 'utf-8');
  const env = {};
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith('#')) continue;
    const m = line.match(/^([A-Z0-9_]+)=(.*)$/);
    if (m) env[m[1]] = m[2];
  }
  return env;
}

const env = loadEnv();
const BASE = 'http://localhost:5174';

// 用户端功能页面（按使用频率排序）
const USER_PAGES = [
  // 核心功能
  { path: '/agent', name: '智能对话', action: 'chat', question: '你好，介绍一下你自己' },
  { path: '/dashboard', name: '工作台', action: 'view' },
  // 数据功能
  { path: '/documents', name: '文档管理', action: 'view' },
  { path: '/reports', name: '财务报告', action: 'view' },
  { path: '/queries', name: '数据查询', action: 'view' },
  // 历史与跟踪
  { path: '/conversations', name: '对话历史', action: 'view' },
  { path: '/kpi', name: 'KPI 看板', action: 'view' },
  // 审计与合规
  { path: '/audit', name: '审计日志', action: 'view' },
  { path: '/approvals', name: '审批管理', action: 'view' },
  { path: '/reflections', name: '反思日志', action: 'view' },
  { path: '/hitl', name: '人工介入', action: 'view' },
];

async function main() {
  const browser = await chromium.launch({
    executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    headless: true,
  });

  const page = await browser.newPage();
  const results = [];
  const consoleErrors = [];
  const apiErrors = [];

  page.on('console', msg => { if (msg.type() === 'error') consoleErrors.push(msg.text()) });
  page.on('pageerror', err => consoleErrors.push('JS: ' + err.message));
  page.on('response', r => {
    const s = r.status();
    if (s === 401 && !r.url().includes('/auth/me')) apiErrors.push(`${s} ${r.url().split('?')[0]}`);
    if (s >= 500) apiErrors.push(`${s} ${r.url().split('?')[0]}`);
  });

  // === 登录 ===
  console.log('=== 登录 ===');
  await page.goto(BASE + '/login', { waitUntil: 'domcontentloaded', timeout: 20000 });
  await page.fill('input[name="username"]', env.FINPILOT_ADMIN_EMAIL || 'admin@finpilot.ai');
  await page.fill('input[name="password"]', env.FINPILOT_ADMIN_PASSWORD || 'w9MIquomakyemjLOzaOChA');
  await page.click('button[type="submit"]');
  await page.waitForURL('**/dashboard', { timeout: 15000 });
  console.log('已登录\n');

  // === 逐个测试页面 ===
  for (const { path, name, action, question } of USER_PAGES) {
    const errBefore = consoleErrors.length;
    const apiBefore = apiErrors.length;
    const result = { name, path, status: '✅', chatOk: false, details: [] };
    let pageHeading = '—';

    try {
      await page.goto(BASE + path, { waitUntil: 'domcontentloaded', timeout: 20000 });
      await page.waitForTimeout(2000);

      // 检查页面内容
      const info = await page.evaluate(() => {
        const h1 = document.querySelector('h1')?.textContent?.trim() || '';
        const h2 = document.querySelector('h2')?.textContent?.trim() || '';
        const main = (document.querySelector('main') || document.body).innerText?.substring(0, 200) || '';
        const errorEl = document.querySelector('[class*="error"], [class*="Error"]');
        const hasError = errorEl && errorEl.textContent?.includes('出错');
        return { h1, h2, main, hasError };
      });

      if (info.hasError) {
        result.status = '❌';
        result.details.push('页面渲染错误');
      }
      if (!info.h1 && !info.h2 && info.main.length < 10) {
        result.status = '⚠️';
        result.details.push('页面内容过少');
      }
      pageHeading = info.h1 || info.h2 || '';

      // Agent Chat 特殊操作：发送消息
      if (action === 'chat' && question) {
        try {
          const textarea = page.locator('textarea, [contenteditable="true"], input[type="text"]').first();
          if (await textarea.isVisible({ timeout: 3000 })) {
            await textarea.fill(question);
            await page.waitForTimeout(500);
            const sendBtn = page.locator('button[type="submit"], button:has-text("发送"), button:has-text("Send")').first();
            if (await sendBtn.isVisible({ timeout: 3000 })) {
              await sendBtn.click();
              // 等待回复（最长 60s）
              await page.waitForTimeout(5000);
              try {
                await page.waitForFunction(() => {
                  const bodies = document.querySelectorAll('[class*="assistant"], [class*="bot"], [class*="message"]');
                  return bodies.length > 0;
                }, { timeout: 50000 });
                result.chatOk = true;
                result.details.push('对话功能正常');
              } catch {
                result.details.push('⚠️ 对话回复超时（60s 未检测到回复）');
              }
            } else {
              result.details.push('⚠️ 未找到发送按钮');
            }
          } else {
            result.details.push('⚠️ 未找到输入框');
          }
        } catch (e) {
          result.details.push('⚠️ 对话交互异常: ' + e.message.substring(0, 40));
        }
      }

      // 检查表格/列表
      const hasTable = await page.evaluate(() => document.querySelectorAll('table').length > 0);
      const hasList = await page.evaluate(() => document.querySelectorAll('li, [class*="list"], [class*="card"]').length > 5);

      const newErr = consoleErrors.length - errBefore;
      const newApi = apiErrors.length - apiBefore;

      result.details.push(`表格:${hasTable ? '✓' : '✗'} 列表元素:${hasList ? '✓' : '✗'}`);
      if (newErr > 0) result.details.push(`新报错:${newErr}`);
      if (newApi > 0) result.details.push(`API异常:${newApi}`);

    } catch (e) {
      result.status = '❌';
      result.details.push('加载失败: ' + e.message.substring(0, 60));
    }

    console.log(`${result.status} ${name.padEnd(12)} | ${result.chatOk ? '💬 ' : ''}${pageHeading.substring(0, 30)} | ${result.details.join(' | ')}`);
    results.push(result);
  }

  // === 汇总 ===
  console.log('\n========================================');
  console.log('=== 用户端功能测试汇总 ===');
  console.log('========================================\n');

  const ok = results.filter(r => r.status === '✅');
  const warn = results.filter(r => r.status === '⚠️');
  const fail = results.filter(r => r.status === '❌');
  const chatOk = results.filter(r => r.chatOk);

  console.log(`页面: ${ok.length}✅ ${warn.length}⚠️ ${fail.length}❌ (共${results.length})`);
  console.log(`对话: ${chatOk.length} 正常`);
  console.log(`API 异常(401/500+): ${apiErrors.length} 个`);
  console.log(`控制台报错: ${consoleErrors.length} 条`);

  if (fail.length > 0) {
    console.log('\n❌ 失败页面:');
    fail.forEach(r => console.log(`  ${r.name} (${r.path}): ${r.details.join('; ')}`));
  }
  if (apiErrors.length > 0) {
    const unique = [...new Set(apiErrors)].filter(u => !u.includes('/auth/me'));
    if (unique.length > 0) {
      console.log('\nAPI 异常 (去重):');
      unique.forEach(u => console.log(`  ${u}`));
    }
  }

  await browser.close();
}

main().catch(e => { console.error('FATAL:', e.message); process.exit(1); });
