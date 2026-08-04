// E2E: 遍历所有设置/管理页面，检查加载、渲染、控制台报错

import { chromium } from 'playwright';
import { readFileSync } from 'fs';

// 加载 .env
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
const ADMIN_EMAIL = env.FINPILOT_ADMIN_EMAIL || 'admin@finpilot.ai';
const ADMIN_PASS = env.FINPILOT_ADMIN_PASSWORD || 'w9MIquomakyemjLOzaOChA';

// 需要访问的所有设置页面（路径 + 中文名）
const SETTINGS_PAGES = [
  // 安全设置（普通用户可见）
  { path: '/security', name: '安全设置' },
  // 用户与权限
  { path: '/users', name: '用户管理' },
  { path: '/api-keys', name: 'API 密钥' },
  { path: '/llm-providers', name: 'LLM 供应商' },
  { path: '/access-policies', name: '访问策略' },
  // 报告
  { path: '/report-subscriptions', name: '报告订阅' },
  { path: '/report-templates', name: '报告模板' },
  // Admin 管理后台
  { path: '/admin', name: '管理仪表盘' },
  { path: '/admin/models', name: '模型管理' },
  { path: '/admin/prompts', name: '提示词管理' },
  { path: '/admin/prompt-deep', name: '深度提示词' },
  { path: '/admin/tools', name: '工具管理' },
  { path: '/admin/tool-monitoring', name: '工具监控' },
  { path: '/admin/context-management', name: '上下文管理' },
  { path: '/admin/skills', name: '技能管理' },
  { path: '/admin/search-engines', name: '搜索引擎' },
  { path: '/admin/mcp-servers', name: 'MCP 服务器' },
  { path: '/admin/sandbox-configs', name: '沙箱配置' },
  { path: '/admin/agents', name: '智能体配置' },
  { path: '/admin/settings', name: '系统设置' },
  { path: '/admin/eval-management', name: '评估管理' },
  { path: '/admin/factor-mining', name: '因子挖掘' },
  { path: '/admin/backtesting', name: '回测' },
  { path: '/admin/workflow-editor', name: '工作流编辑器' },
  { path: '/admin/runtime-logs', name: '运行日志' },
];

async function main() {
  const browser = await chromium.launch({
    executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    headless: true,
  });

  const page = await browser.newPage();
  const results = [];
  const errors = [];

  // 收集控制台错误
  page.on('console', msg => {
    if (msg.type() === 'error') errors.push(msg.text());
  });
  page.on('pageerror', err => {
    errors.push('PAGE_ERROR: ' + err.message);
  });

  // 收集 API 401/500
  page.on('response', r => {
    if (r.status() === 401 || r.status() >= 500) {
      results.push({ type: 'api_error', url: r.url(), status: r.status() });
    }
  });

  // === 登录 ===
  console.log('=== 登录 ===');
  await page.goto(BASE + '/login', { waitUntil: 'domcontentloaded', timeout: 20000 });
  await page.fill('input[name="username"]', ADMIN_EMAIL);
  await page.fill('input[name="password"]', ADMIN_PASS);
  await page.click('button[type="submit"]');
  await page.waitForURL('**/dashboard', { timeout: 15000 });
  console.log('已登录');

  // === 逐个访问设置页面 ===
  for (const { path, name } of SETTINGS_PAGES) {
    const erBefore = errors.length;
    try {
      await page.goto(BASE + path, { waitUntil: 'domcontentloaded', timeout: 15000 });
      await page.waitForTimeout(1500); // 等待 React 渲染

      // 检查页面是否有可见内容
      const bodyText = await page.evaluate(() => document.body.innerText?.substring(0, 200) || '');
      const hasContent = bodyText.length > 5 && !bodyText.includes('页面出错了');
      const newErrs = errors.length - erBefore;

      const status = hasContent ? '✅' : '⚠️';
      console.log(`${status} ${name.padEnd(14)} | /${path.padEnd(24)} | ${hasContent ? '内容正常' : '内容异常'} | 新报错:${newErrs}`);
    } catch (e) {
      console.log(`❌ ${name.padEnd(14)} | /${path.padEnd(24)} | 加载失败: ${e.message.substring(0, 60)}`);
    }
  }

  // === 统计 ===
  const uniqueApiErrs = [...new Set(results.map(r => r.url).filter(u => !u.includes('/auth/me')))];

  console.log('\n=== 汇总 ===');
  console.log(`页面总数: ${SETTINGS_PAGES.length}`);
  console.log(`控制台报错: ${errors.length} 条`);
  console.log(`异常 API (401/500+, 去重): ${uniqueApiErrs.length} 个`);
  if (uniqueApiErrs.length > 0) {
    uniqueApiErrs.forEach(u => console.log(`  - ${u}`));
  }
  if (errors.length > 0) {
    console.log('\n控制台错误一览:');
    const uniqueErrs = [...new Set(errors)].slice(0, 15);
    uniqueErrs.forEach(e => console.log(`  - ${e.substring(0, 120)}`));
  }

  await browser.close();
}

main().catch(e => { console.error('FATAL:', e.message); process.exit(1); });
