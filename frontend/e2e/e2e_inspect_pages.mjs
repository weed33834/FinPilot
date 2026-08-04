// 深度检查每个设置页面的实际功能内容

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

const PAGES = [
  { path: '/security', name: '安全设置', expectCRUD: false },
  { path: '/users', name: '用户管理', expectCRUD: true },
  { path: '/api-keys', name: 'API 密钥', expectCRUD: true },
  { path: '/llm-providers', name: 'LLM 供应商', expectCRUD: true },
  { path: '/access-policies', name: '访问策略', expectCRUD: true },
  { path: '/report-subscriptions', name: '报告订阅', expectCRUD: true },
  { path: '/report-templates', name: '报告模板', expectCRUD: true },
  { path: '/admin/models', name: '模型管理', expectCRUD: true },
  { path: '/admin/prompts', name: '提示词管理', expectCRUD: true },
  { path: '/admin/tools', name: '工具管理', expectCRUD: true },
  { path: '/admin/skills', name: '技能管理', expectCRUD: true },
  { path: '/admin/search-engines', name: '搜索引擎', expectCRUD: true },
  { path: '/admin/mcp-servers', name: 'MCP 服务器', expectCRUD: true },
  { path: '/admin/sandbox-configs', name: '沙箱配置', expectCRUD: true },
  { path: '/admin/agents', name: '智能体配置', expectCRUD: true },
  { path: '/admin/settings', name: '系统设置', expectCRUD: false },
  { path: '/admin/eval-management', name: '评估管理', expectCRUD: true },
  { path: '/admin/runtime-logs', name: '运行日志', expectCRUD: false },
  { path: '/admin/factor-mining', name: '因子挖掘', expectCRUD: false },
  { path: '/admin/backtesting', name: '回测', expectCRUD: false },
];

async function inspectPage(page, { path, name, expectCRUD }) {
  const result = { name, path, issues: [], features: [] };
  
  try {
    await page.goto(BASE + path, { waitUntil: 'domcontentloaded', timeout: 15000 });
    await page.waitForTimeout(2000);

    // 获取页面文本内容
    const info = await page.evaluate(() => {
      const h1 = document.querySelector('h1')?.textContent?.trim() || '';
      const h2 = document.querySelector('h2')?.textContent?.trim() || '';
      
      // 按钮
      const buttons = [...document.querySelectorAll('button')]
        .filter(b => b.offsetParent !== null)
        .map(b => b.textContent?.trim()?.substring(0, 30))
        .filter(Boolean);
      
      // 输入框
      const inputs = [...document.querySelectorAll('input, textarea, select')]
        .filter(el => el.offsetParent !== null)
        .map(el => el.getAttribute('placeholder') || el.getAttribute('name') || el.tagName)
        .filter(Boolean);
      
      // 表格
      const tables = document.querySelectorAll('table');
      const hasTable = tables.length > 0;
      const tableHeaders = hasTable 
        ? [...tables[0].querySelectorAll('th')].map(th => th.textContent?.trim()).filter(Boolean)
        : [];
      
      // 空状态
      const emptyTexts = [
        ...document.querySelectorAll('[class*="empty"], [class*="Empty"], [class*="no-data"], [class*="NoData"]')
      ].map(el => el.textContent?.trim()?.substring(0, 50)).filter(Boolean);
      
      // 整体可见文本（前 300 字）
      const body = document.body.innerText?.substring(0, 400) || '';
      
      return { h1, h2, buttons, inputs: inputs.slice(0, 10), hasTable, tableHeaders, emptyTexts, body };
    });

    // 分析
    result.features = {
      heading: info.h1 || info.h2,
      buttons: info.buttons,
      inputs: info.inputs,
      hasTable: info.hasTable,
      tableHeaders: info.tableHeaders,
      emptyTexts: info.emptyTexts,
      bodyPreview: info.body.substring(0, 100),
    };

    // 检查缺失
    if (expectCRUD) {
      const btnTexts = info.buttons.join(' ');
      const hasChinese = /[\u4e00-\u9fa5]/.test(info.body);
      
      if (!hasChinese) {
        result.issues.push('⚠️ 页面无中文内容（可能未加载）');
      }
      if (!btnTexts.includes('新建') && !btnTexts.includes('创建') && !btnTexts.includes('添加') && !btnTexts.includes('新增') && !btnTexts.includes('Add') && !btnTexts.includes('Create')) {
        result.issues.push('❌ 缺少新建/创建按钮');
      }
      if (info.hasTable && info.tableHeaders.length === 0) {
        result.issues.push('⚠️ 有表格但无表头');
      }
      if (info.emptyTexts.length === 0 && !info.hasTable) {
        // 可能是空列表或没数据
      }
      if (info.buttons.length === 0) {
        result.issues.push('❌ 页面无任何可操作按钮');
      }
    }

    if (info.body.includes('页面出错了') || info.body.includes('Error')) {
      result.issues.push('❌ 页面渲染错误');
    }

  } catch (e) {
    result.issues.push(`❌ 加载失败: ${e.message.substring(0, 60)}`);
  }

  return result;
}

async function main() {
  const browser = await chromium.launch({
    executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    headless: true,
  });

  const page = await browser.newPage();

  // === 登录 ===
  console.log('=== 登录 ===');
  await page.goto(BASE + '/login', { waitUntil: 'domcontentloaded', timeout: 20000 });
  await page.fill('input[name="username"]', env.FINPILOT_ADMIN_EMAIL || 'admin@finpilot.ai');
  await page.fill('input[name="password"]', env.FINPILOT_ADMIN_PASSWORD || 'w9MIquomakyemjLOzaOChA');
  await page.click('button[type="submit"]');
  await page.waitForURL('**/dashboard', { timeout: 15000 });
  console.log('已登录\n');

  const results = [];
  for (const p of PAGES) {
    console.log(`检查: ${p.name} (${p.path})`);
    const r = await inspectPage(page, p);
    
    console.log(`  标题: ${r.features.heading || '(无)'}`);
    console.log(`  按钮: ${r.features.buttons?.join(', ') || '(无)'}`);
    console.log(`  表格: ${r.features.hasTable ? r.features.tableHeaders?.join(' | ') : '无'}`);
    console.log(`  空状态: ${r.features.emptyTexts?.join('; ') || '(无)'}`);
    if (r.issues.length > 0) {
      r.issues.forEach(i => console.log(`  ${i}`));
    }
    console.log('');
    results.push(r);
  }

  // === 汇总 ===
  console.log('========================================');
  console.log('=== 功能缺失汇总 ===');
  console.log('========================================\n');
  
  const withIssues = results.filter(r => r.issues.length > 0);
  if (withIssues.length === 0) {
    console.log('✅ 所有页面功能完整，无明显缺失');
  } else {
    withIssues.forEach(r => {
      console.log(`【${r.name}】${r.path}`);
      r.issues.forEach(i => console.log(`  ${i}`));
    });
  }
  
  // CRUD 功能检查
  console.log('\n=== CRUD 功能完整性 ===');
  results.filter(r => PAGES.find(p => p.path === r.path)?.expectCRUD).forEach(r => {
    const btns = r.features.buttons || [];
    const hasCreate = btns.some(b => /新建|创建|添加|新增|Add|Create|上传/i.test(b));
    const hasDelete = btns.some(b => /删除|Delete|Remove/i.test(b)) || r.features.tableHeaders?.some(h => /操作|Actions/i.test(h));
    const hasEdit = btns.some(b => /编辑|Edit|修改/i.test(b)) || r.features.tableHeaders?.some(h => /操作|Actions/i.test(h));
    const status = hasCreate ? '✅' : '⚠️';
    console.log(`${status} ${r.name.padEnd(12)} 创建:${hasCreate?'✓':'✗'} 编辑:${hasEdit?'✓':'?'} 删除:${hasDelete?'✓':'?'}  表格:${r.features.hasTable?'✓':'✗'}`);
  });

  await browser.close();
}

main().catch(e => { console.error('FATAL:', e.message); process.exit(1); });
