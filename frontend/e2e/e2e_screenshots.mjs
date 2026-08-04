// 对所有页面截图，用于肉眼检查 UI 瑕疵

import { chromium } from 'playwright';
import { readFileSync } from 'fs';
import { resolve } from 'path';

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
const SCREENSHOT = resolve('screenshots');

async function main() {
  const browser = await chromium.launch({
    executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    headless: true,
  });

  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

  // Login
  await page.goto(BASE + '/login', { waitUntil: 'domcontentloaded', timeout: 20000 });
  await page.fill('input[name="username"]', env.FINPILOT_ADMIN_EMAIL || 'admin@finpilot.ai');
  await page.fill('input[name="password"]', env.FINPILOT_ADMIN_PASSWORD || 'w9MIquomakyemjLOzaOChA');
  await page.click('button[type="submit"]');
  await page.waitForURL('**/dashboard', { timeout: 15000 });

  // 需要截图的所有页面（含操作后的截图）
  const shots = [
    // 用户端核心
    { path: '/agent', name: '01-agent-chat', action: null },
    { path: '/dashboard', name: '02-dashboard', action: null },
    { path: '/documents', name: '03-documents', action: null },
    { path: '/reports', name: '04-reports', action: null },
    { path: '/queries', name: '05-queries', action: null },
    { path: '/conversations', name: '06-conversations', action: null },
    { path: '/kpi', name: '07-kpi', action: null },
    { path: '/audit', name: '08-audit', action: null },
    { path: '/approvals', name: '09-approvals', action: null },
    { path: '/reflections', name: '10-reflections', action: null },
    { path: '/hitl', name: '11-hitl', action: null },
    { path: '/security', name: '12-security', action: null },
    // 管理后台
    { path: '/admin', name: '20-admin-dashboard', action: null },
    { path: '/admin/models', name: '21-admin-models', action: null },
    { path: '/admin/prompts', name: '22-admin-prompts', action: null },
    { path: '/admin/tools', name: '23-admin-tools', action: null },
    { path: '/admin/skills', name: '24-admin-skills', action: null },
    { path: '/admin/search-engines', name: '25-admin-search', action: null },
    { path: '/admin/mcp-servers', name: '26-admin-mcp', action: null },
    { path: '/admin/sandbox-configs', name: '27-admin-sandbox', action: null },
    { path: '/admin/agents', name: '28-admin-agents', action: null },
    { path: '/admin/settings', name: '29-admin-settings', action: null },
    { path: '/admin/runtime-logs', name: '30-admin-logs', action: null },
    // 权限管理
    { path: '/users', name: '31-users', action: null },
    { path: '/api-keys', name: '32-apikeys', action: null },
    { path: '/llm-providers', name: '33-llm-providers', action: null },
    { path: '/access-policies', name: '34-access-policies', action: null },
    { path: '/report-subscriptions', name: '35-report-subs', action: null },
    { path: '/report-templates', name: '36-report-templates', action: null },
  ];

  for (const s of shots) {
    try {
      await page.goto(BASE + s.path, { waitUntil: 'domcontentloaded', timeout: 15000 });
      await page.waitForTimeout(2000);
      await page.screenshot({ path: resolve(SCREENSHOT, s.name + '.png'), fullPage: false });
      console.log('OK: ' + s.name);
    } catch (e) {
      console.log('FAIL: ' + s.name + ' - ' + e.message.substring(0, 50));
    }
  }

  await browser.close();
  console.log('\nDone. ' + shots.length + ' screenshots in ' + SCREENSHOT);
}

main().catch(e => { console.error('FATAL:', e.message); process.exit(1); });
