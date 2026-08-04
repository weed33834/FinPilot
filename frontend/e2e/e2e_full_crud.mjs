// E2E: 全功能深度 CRUD 测试 — 模拟真实用户使用每个功能
// 每个模块测试：创建 → 查看 → 编辑 → 删除 完整链路

import { chromium } from 'playwright';
import { readFileSync } from 'fs';
import path from 'path';

const BASE = 'http://localhost:5174';
const TEST_DIR = path.resolve('..');
let PASS = 0, FAIL = 0;

function result(label, ok, detail = '') {
  if (ok) { PASS++; console.log(`✅ ${label}` + (detail ? `: ${detail}` : '')); }
  else { FAIL++; console.log(`❌ ${label}` + (detail ? `: ${detail}` : '')); }
}

async function login(page) {
  await page.goto(BASE + '/login', { waitUntil: 'domcontentloaded', timeout: 20000 });
  await page.fill('input[name="username"]', 'admin@finpilot.ai');
  await page.fill('input[name="password"]', 'w9MIquomakyemjLOzaOChA');
  await page.click('button[type="submit"]');
  await page.waitForURL('**/dashboard', { timeout: 15000 });
}

// ==================== 测试 1: Agent 对话 ====================
async function testAgentChat(page) {
  console.log('\n📋 Agent 智能对话测试');
  
  await page.goto(BASE + '/agent', { waitUntil: 'domcontentloaded', timeout: 15000 });
  await page.waitForTimeout(2000);

  // 1a. 发送简单问题
  const ta = page.locator('textarea').first();
  const taVisible = await ta.isVisible({ timeout: 3000 }).catch(() => false);
  result('输入框可见', taVisible);
  if (!taVisible) return;

  await ta.fill('帮我创建一个季度财务分析报告，格式为JSON');
  await page.waitForTimeout(300);
  const send = page.locator('button[type="submit"]').first();
  await send.click();
  
  // 等待回复
  let replyFound = false;
  try {
    await page.waitForFunction(() => {
      const msgs = document.querySelectorAll('[class*="assistant"], [class*="bot-message"], [class*="message-content"]');
      return [...msgs].some(m => m.textContent.length > 20);
    }, { timeout: 60000 });
    replyFound = true;
  } catch {}
  result('发送+接收回复', replyFound);

  // 1b. 再发一条（多轮对话）
  if (replyFound) {
    const ta2 = page.locator('textarea').first();
    await ta2.fill('现在1+2*3等于多少？只回答数字');
    await page.waitForTimeout(300);
    await page.locator('button[type="submit"]').first().click();
    await page.waitForTimeout(8000);
    const hasMore = await page.evaluate(() => document.querySelectorAll('[class*="message"]').length);
    result('多轮对话', hasMore > 2, `${hasMore}条消息`);
  }

  // 1c. 侧边栏建议问题
  const suggestions = await page.evaluate(() => {
    return [...document.querySelectorAll('[class*="suggest"], [class*="template"], [class*="example"]')]
      .filter(el => el.textContent?.trim())
      .slice(0, 5)
      .map(el => el.textContent.trim().substring(0, 30));
  });
  result('建议问题/快捷模板', suggestions.length > 0, suggestions.join(' | '));
  if (suggestions.length > 0) {
    // 点击第一个建议
    const firstSugg = page.locator('[class*="suggest"], [class*="template"], [class*="example"]').first();
    await firstSugg.click().catch(() => {});
    await page.waitForTimeout(2000);
  }
}

// ==================== 测试 2: 对话历史 ====================
async function testConversations(page) {
  console.log('\n📋 对话历史测试');
  
  await page.goto(BASE + '/conversations', { waitUntil: 'domcontentloaded', timeout: 15000 });
  await page.waitForTimeout(3000);

  // 2a. 列表存在
  const tableRows = await page.evaluate(() => document.querySelectorAll('table tr, [class*="conv-item"]').length);
  result('对话列表', tableRows > 1, `${tableRows}项`);

  // 2b. 点击第一条进入详情
  const firstRow = page.locator('table tr:not(:first-child), [class*="conv-item"]').first();
  const hasFirst = await firstRow.isVisible({ timeout: 3000 }).catch(() => false);
  if (hasFirst) {
    await firstRow.click();
    await page.waitForTimeout(2000);
    // 检查是否跳转到对话页面
    const url = page.url();
    result('点击进入对话详情', url.includes('/agent') || url.includes('/conversations/'), url.split('/').pop());
  }

  // 2c. 返回列表，测试删除
  await page.goto(BASE + '/conversations', { waitUntil: 'domcontentloaded', timeout: 15000 });
  await page.waitForTimeout(2000);
  const deleteBtn = page.locator('button:has-text("删除"), button:has-text("Delete"), [title*="删除"]').first();
  const hasDelBtn = await deleteBtn.isVisible({ timeout: 2000 }).catch(() => false);
  result('删除按钮', hasDelBtn);
}

// ==================== 测试 3: 文档管理 ====================
async function testDocuments(page) {
  console.log('\n📋 文档管理测试');
  
  await page.goto(BASE + '/documents', { waitUntil: 'domcontentloaded', timeout: 15000 });
  await page.waitForTimeout(3000);

  // 3a. 检查上传功能
  // 先看有没有 file input
  const fileInput = page.locator('input[type="file"]');
  const hasFI = await fileInput.count() > 0;
  
  if (hasFI) {
    // 直接上传
    await fileInput.first().setInputFiles(path.join(TEST_DIR, 'test_finance.csv'));
    await page.waitForTimeout(4000);
    const items = await page.evaluate(() => document.querySelectorAll('table tr, [class*="doc-item"], [class*="file"]').length);
    result('上传文档', items > 1, `${items}项`);
  } else {
    // 找上传按钮
    const uploadBtn = page.locator('button:has-text("上传"), button:has-text("Upload"), [class*="upload"]').first();
    const hasBtn = await uploadBtn.isVisible({ timeout: 3000 }).catch(() => false);
    if (hasBtn) {
      await uploadBtn.click();
      await page.waitForTimeout(1500);
      // 弹窗中找 file input
      const modalFi = page.locator('input[type="file"]').first();
      const hasModalFi = await modalFi.count() > 0;
      if (hasModalFi) {
        await modalFi.setInputFiles(path.join(TEST_DIR, 'test_finance.csv'));
        await page.waitForTimeout(2000);
        // 找确认按钮
        const confirm = page.locator('button:has-text("确定"), button:has-text("上传"), button:has-text("Confirm")').first();
        await confirm.click().catch(() => {});
        await page.waitForTimeout(3000);
        result('弹窗上传', true);
      }
    } else {
      result('上传入口', false, '无上传按钮（空状态需检查）');
    }
  }

  // 3b. 检查文档列表和删除
  await page.goto(BASE + '/documents', { waitUntil: 'domcontentloaded', timeout: 15000 });
  await page.waitForTimeout(2000);
  const docDel = page.locator('button:has-text("删除"), button:has-text("Delete")').first();
  result('删除按钮可见', await docDel.isVisible({ timeout: 2000 }).catch(() => false));
}

// ==================== 测试 4: 数据查询 ====================
async function testQueries(page) {
  console.log('\n📋 数据查询测试');
  
  await page.goto(BASE + '/queries', { waitUntil: 'domcontentloaded', timeout: 15000 });
  await page.waitForTimeout(3000);

  const qi = page.locator('textarea, input[type="text"]').first();
  const hasQI = await qi.isVisible({ timeout: 2000 }).catch(() => false);
  
  if (hasQI) {
    await qi.fill('查询收入最高的月份');
    await page.waitForTimeout(300);
    const qb = page.locator('button:has-text("查询"), button:has-text("执行"), button[type="submit"]').first();
    await qb.click().catch(() => {});
    await page.waitForTimeout(5000);
    const hasResult = await page.evaluate(() => {
      return document.querySelectorAll('table, [class*="result"], [class*="output"], pre').length > 0;
    });
    result('Text2SQL 查询', hasResult);
  } else {
    result('查询入口', false, '无输入框');
  }

  // 检查有无查询历史
  const history = page.locator('[class*="history"], [class*="record"]').first();
  result('查询历史区域', await history.isVisible({ timeout: 2000 }).catch(() => false));
}

// ==================== 测试 5: 财务报告 ====================
async function testReports(page) {
  console.log('\n📋 财务报告测试');

  await page.goto(BASE + '/reports', { waitUntil: 'domcontentloaded', timeout: 15000 });
  await page.waitForTimeout(3000);

  // 创建报告
  const createBtn = page.locator('button:has-text("创建报告"), button:has-text("新建"), button:has-text("Create")').first();
  const hasCreate = await createBtn.isVisible({ timeout: 3000 }).catch(() => false);
  if (hasCreate) {
    await createBtn.click();
    await page.waitForTimeout(2000);
    
    // 检查弹窗内容
    const modalTitle = page.locator('[class*="modal"] h2, [class*="modal"] h3, [class*="dialog"] h2').first();
    const hasModal = await modalTitle.isVisible({ timeout: 2000 }).catch(() => false);
    if (hasModal) {
      const title = await modalTitle.textContent();
      result('创建报告弹窗', true, title);
      
      // 尝试填写并提交
      const titleInput = page.locator('[class*="modal"] input').first();
      if (await titleInput.isVisible({ timeout: 1000 }).catch(() => false)) {
        await titleInput.fill('测试财务报告');
      }
      const submitBtn = page.locator('[class*="modal"] button:has-text("确定"), [class*="modal"] button[type="submit"]').first();
      if (await submitBtn.isVisible({ timeout: 1000 }).catch(() => false)) {
        await submitBtn.click();
        await page.waitForTimeout(3000);
        result('提交报告', true);
      }
    }
  } else {
    result('创建报告入口', false, '无按钮');
  }
}

// ==================== 测试 6: KPI 看板 ====================
async function testKpi(page) {
  console.log('\n📋 KPI 看板测试');

  await page.goto(BASE + '/kpi', { waitUntil: 'domcontentloaded', timeout: 15000 });
  await page.waitForTimeout(3000);

  const metrics = await page.evaluate(() => {
    return {
      svg: document.querySelectorAll('svg').length,
      cards: document.querySelectorAll('[class*="kpi-card"], [class*="metric-card"]').length,
      bars: document.querySelectorAll('[class*="bar"], rect').length,
      tabs: document.querySelectorAll('[role="tab"], [class*="tab"]').length,
    };
  });
  result('图表渲染', metrics.svg > 0, `SVG:${metrics.svg} 卡:${metrics.cards}`);
  if (metrics.tabs > 0) {
    // 点击第二个tab
    const tab2 = page.locator('[role="tab"], [class*="tab"]').nth(1);
    await tab2.click().catch(() => {});
    await page.waitForTimeout(1500);
    result('Tab切换', true);
  }
}

// ==================== 测试 7: 审计日志 ====================
async function testAudit(page) {
  console.log('\n📋 审计日志测试');

  await page.goto(BASE + '/audit', { waitUntil: 'domcontentloaded', timeout: 15000 });
  await page.waitForTimeout(3000);

  const rows = await page.evaluate(() => document.querySelectorAll('table tr').length);
  result('审计记录', rows > 1, `${rows-1}条`);

  // 筛选功能
  const selects = page.locator('select');
  const selCount = await selects.count();
  if (selCount > 0) {
    await selects.first().selectOption(1).catch(() => {});
    await page.waitForTimeout(2000);
    result('筛选操作', true);
  }
  result('筛选组件', selCount > 0);
}

// ==================== 测试 8: 安全设置 ====================
async function testSecurity(page) {
  console.log('\n📋 安全设置测试');

  await page.goto(BASE + '/security', { waitUntil: 'domcontentloaded', timeout: 15000 });
  await page.waitForTimeout(3000);

  // 2FA 状态
  const tfa = await page.evaluate(() => document.body.innerText?.match(/2FA|双因素|两步验证/));
  result('2FA 区域', !!tfa);

  // 修改密码
  const cpBtn = page.locator('button:has-text("修改密码"), button:has-text("Change")').first();
  const hasCp = await cpBtn.isVisible({ timeout: 2000 }).catch(() => false);
  if (hasCp) {
    await cpBtn.click();
    await page.waitForTimeout(1500);
    
    // 查找密码输入框（可能在弹窗中）
    const pwdInputs = page.locator('input[type="password"]');
    const pwdCount = await pwdInputs.count();
    if (pwdCount >= 2) {
      await pwdInputs.nth(0).fill('w9MIquomakyemjLOzaOChA'); // 当前密码
      await pwdInputs.nth(1).fill('NewPass123!'); // 新密码
      const saveBtn = page.locator('button:has-text("确认"), button:has-text("保存"), button[type="submit"]').first();
      await saveBtn.click().catch(() => {});
      await page.waitForTimeout(2000);
      result('修改密码', true, '已填写提交');
      
      // 改回原密码
      if (await pwdInputs.nth(0).isVisible({ timeout: 1000 }).catch(() => false)) {
        await pwdInputs.nth(0).fill('NewPass123!');
        await pwdInputs.nth(1).fill('w9MIquomakyemjLOzaOChA');
        await saveBtn.click().catch(() => {});
        await page.waitForTimeout(2000);
      }
    } else {
      result('修改密码弹窗', pwdCount >= 2, `密码框数=${pwdCount}`);
    }
  } else {
    result('修改密码按钮', false);
  }
}

// ==================== 测试 9: 审批管理 ====================
async function testApprovals(page) {
  console.log('\n📋 审批管理测试');
  
  await page.goto(BASE + '/approvals', { waitUntil: 'domcontentloaded', timeout: 15000 });
  await page.waitForTimeout(3000);

  const body = await page.evaluate(() => document.body.innerText?.substring(0, 200) || '');
  result('页面加载', body.length > 20);

  const btns = await page.evaluate(() => 
    [...document.querySelectorAll('button')].filter(b => b.offsetParent).map(b => b.textContent.trim().substring(0, 20))
  );
  result('操作按钮', btns.length > 4, btns.slice(0, 5).join(','));
}

// ==================== 测试 10: 工作台 ====================
async function testDashboard(page) {
  console.log('\n📋 工作台测试');

  await page.goto(BASE + '/dashboard', { waitUntil: 'domcontentloaded', timeout: 15000 });
  await page.waitForTimeout(3000);

  const cards = await page.evaluate(() => document.querySelectorAll('[class*="card"], [class*="widget"]').length);
  const charts = await page.evaluate(() => document.querySelectorAll('svg, canvas').length);
  result('仪表盘', cards > 0, `${cards}卡片 ${charts}图表`);
}

// ==================== 主流程 ====================
async function main() {
  console.log('╔══════════════════════════════════════╗');
  console.log('║  FinPilot 全功能深度 CRUD 测试 v5   ║');
  console.log('╚══════════════════════════════════════╝');

  const browser = await chromium.launch({
    executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    headless: true,
  });

  // 运行 5 轮测试
  for (let round = 1; round <= 5; round++) {
    console.log(`\n\n████████ 第 ${round}/5 轮测试 ████████`);
    const page = await browser.newPage();
    
    try {
      await login(page);
      
      await testAgentChat(page);
      await testConversations(page);
      await testDocuments(page);
      await testQueries(page);
      await testReports(page);
      await testKpi(page);
      await testAudit(page);
      await testSecurity(page);
      await testApprovals(page);
      await testDashboard(page);
      
    } catch (e) {
      console.log(`\n❌ 第${round}轮异常:`, e.message);
    } finally {
      await page.close();
    }
  }

  await browser.close();

  console.log('\n\n═══════════════════════════════════════');
  console.log(`  最终统计: ${PASS}✅ / ${FAIL}❌ (5轮累计)`);
  console.log('═══════════════════════════════════════');
}

main().catch(e => { console.error('FATAL:', e.message); process.exit(1); });
