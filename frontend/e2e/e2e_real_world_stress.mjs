// 真实财务分析场景压力测试 — 模拟分析师日常工作流
// 测试项：多轮深度对话 + 文档上传解析 + 报告生成 + 数据查询 + 对话追溯

import { chromium } from 'playwright';
import { readFileSync, writeFileSync } from 'fs';
import { resolve } from 'path';

const BASE = 'http://localhost:5174';

// 生成模拟年报数据（100 行 × 12 列，约 5KB）
const FINANCIAL_DATA = '日期,营业收入,营业成本,营业利润,净利润,总资产,总负债,股东权益,经营活动现金流,投资活动现金流,融资活动现金流,研发费用\n'
  + Array.from({length:24}, (_,i) => {
    const y=2024-Math.floor(i/4); const q=i%4+1;
    const rev = 80000000 + Math.floor(Math.random()*40000000);
    const cost = Math.floor(rev * (0.6 + Math.random()*0.15));
    const profit = rev - cost;
    return `2024-Q${q},${rev},${cost},${profit},${Math.floor(profit*0.75)},${Math.floor(rev*1.5)},${Math.floor(cost*1.2)},${Math.floor(rev*0.8)},${Math.floor(profit*0.5 + (Math.random()-0.5)*10000000)},${Math.floor((Math.random()-0.5)*20000000)},${Math.floor((Math.random()-0.5)*15000000)},${Math.floor(rev*0.08)}`;
  }).join('\n');

writeFileSync(resolve('..', 'test_annual_report.csv'), FINANCIAL_DATA);

const TASKS = [
  // === 场景 A：财务分析深度对话（3 轮追问） ===
  {
    name: '场景A-1: 利润分析',
    steps: [
      { type: 'chat', question: '一家公司2024年总收入1.2亿，成本7200万，财务费用800万，所得税率25%，请算出净利润是多少？按步骤给出计算过程。', verify: /净利润/ },
    ]
  },
  {
    name: '场景A-2: 追问杜邦分析',
    steps: [
      { type: 'chat', question: '基于上一轮的财务数据，做杜邦分析：ROE拆解为净利率×资产周转率×权益乘数。假设总资产2亿，股东权益8000万。', verify: /ROE|净资产收益率/ },
    ]
  },
  {
    name: '场景A-3: 行业对比',
    steps: [
      { type: 'chat', question: '上面这个公司的净利润率和ROE，在制造业中处于什么水平？如果行业平均净利润率8%、平均ROE 12%，给出对比分析。', verify: /对比|行业|平均/ },
    ]
  },

  // === 场景 B：文档上传 + 解析 + 交叉查询 ===
  {
    name: '场景B-1: 上传年报CSV',
    steps: [
      { type: 'upload', file: resolve('..', 'test_annual_report.csv'), verify: /上传成功|解析|indexed/i },
    ]
  },

  // === 场景 C：多表关联 Text2SQL ===
  {
    name: '场景C: 收入趋势SQL',
    steps: [
      { type: 'query', sql: '请查询2024年每个季度的营业收入变化趋势，按季度排序', verify: /Q\d|季度|收入/ },
    ]
  },

  // === 场景 D：报告生成流程 ===
  {
    name: '场景D: 生成财务报告',
    steps: [
      { type: 'report', title: '2024年度财务分析报告', template: '年度分析模板', period: '2024', verify: /创建|生成/ },
    ]
  },

  // === 场景 E：多轮对话上下文记忆 ===
  {
    name: '场景E-1: 上下文保持',
    steps: [
      { type: 'chat', question: '我之前提到的公司，如果2025年营收增长15%，成本率降到62%，新净利润是多少？', verify: /净利润|千万|万/ },
    ]
  },
  {
    name: '场景E-2: 继续追问',
    steps: [
      { type: 'chat', question: '按新数据更新杜邦分析，给出ROE变化', verify: /ROE|净资产收益率/ },
    ]
  },
];

async function runTask(page, task) {
  console.log(`\n--- ${task.name} ---`);
  for (const step of task.steps) {
    try {
      if (step.type === 'chat') {
        await page.goto(BASE + '/agent', { waitUntil: 'domcontentloaded', timeout: 15000 });
        await page.waitForTimeout(2000);
        const ta = page.locator('textarea').first();
        if (!await ta.isVisible({ timeout: 3000 }).catch(() => false)) {
          console.log(`  ❌ 输入框不可见`);
          return false;
        }
        await ta.fill(step.question);
        await page.waitForTimeout(300);
        await page.locator('button[type="submit"]').first().click();

        // 等待回复（最多 120s，大任务需要更久）
        let replied = false;
        try {
          await page.waitForFunction((pattern) => {
            return document.body.innerText.length > 200 && 
              new RegExp(pattern).test(document.body.innerText);
          }, step.verify.source.replace(/[\/]/g,''), { timeout: 120000 });
          replied = true;
        } catch {}
        
        if (replied) {
          const reply = await page.evaluate(() => {
            const msgs = document.querySelectorAll('[class*="assistant"], [class*="bot-message"], [class*="message"]');
            const last = msgs[msgs.length - 1];
            return last?.textContent?.substring(0, 120) || '';
          });
          console.log(`  ✅ 回复: ${reply}`);
          return true;
        } else {
          console.log(`  ⚠️ 回复超时(120s)`);
          return false;
        }
      }
      
      else if (step.type === 'upload') {
        await page.goto(BASE + '/documents', { waitUntil: 'domcontentloaded', timeout: 15000 });
        await page.waitForTimeout(3000);
        // 上传流程
        const selectBtn = page.locator('button:has-text("选择文件")').first();
        if (await selectBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
          await selectBtn.click();
          await page.waitForTimeout(500);
          await page.locator('input[type="file"]').first().setInputFiles(step.file);
          await page.waitForTimeout(1000);
          const uploadBtn = page.locator('button:has-text("上传并解析")').first();
          if (await uploadBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
            await uploadBtn.click();
            await page.waitForTimeout(8000);
            // 检查是否出现新文档
            const items = await page.evaluate(() => document.querySelectorAll('table tr').length);
            console.log(`  ✅ 上传完成，文档数=${items-1}`);
            return items > 1;
          }
        }
        console.log(`  ❌ 上传失败`);
        return false;
      }
      
      else if (step.type === 'query') {
        await page.goto(BASE + '/queries', { waitUntil: 'domcontentloaded', timeout: 15000 });
        await page.waitForTimeout(3000);
        const qi = page.locator('.query-input').first();
        if (await qi.isVisible({ timeout: 2000 }).catch(() => false)) {
          await qi.fill(step.sql);
          await page.waitForTimeout(300);
          await page.locator('button[type="submit"]').first().click();
          await page.waitForTimeout(10000);
          const hasResult = await page.evaluate(() => {
            const tables = document.querySelectorAll('table');
            const pre = document.querySelector('pre');
            return tables.length > 0 || (pre && pre.textContent.length > 20);
          });
          console.log(`  ${hasResult ? '✅' : '⚠️'} 查询结果: ${hasResult}`);
          return hasResult;
        }
        console.log(`  ❌ 查询输入框不可见`);
        return false;
      }
      
      else if (step.type === 'report') {
        await page.goto(BASE + '/reports', { waitUntil: 'domcontentloaded', timeout: 15000 });
        await page.waitForTimeout(3000);
        const createBtn = page.locator('button:has-text("创建报告")').first();
        if (await createBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
          await createBtn.click();
          await page.waitForTimeout(2000);
          // 填写表单
          const inputs = page.locator('input');
          const inputCount = await inputs.count();
          if (inputCount > 0) {
            await inputs.first().fill(step.title);
            const submit = page.locator('button:has-text("确定"), button:has-text("创建"), button[type="submit"]').first();
            if (await submit.isVisible({ timeout: 1000 }).catch(() => false)) {
              await submit.click();
              await page.waitForTimeout(5000);
              console.log(`  ✅ 报告已提交`);
              return true;
            }
          }
        }
        console.log(`  ⚠️ 创建报告流程不完整`);
        return false;
      }
    } catch(e) {
      console.log(`  ❌ 异常: ${e.message.substring(0,60)}`);
      return false;
    }
  }
}

async function main() {
  console.log('═══════════════════════════════════════');
  console.log('  FinPilot 真实场景压力测试');
  console.log('  5 大场景 × 7 个子任务');
  console.log('═══════════════════════════════════════\n');

  const browser = await chromium.launch({
    executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    headless: true,
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

  // Login
  await page.goto(BASE + '/login', { waitUntil: 'domcontentloaded', timeout: 20000 });
  await page.fill('input[name="username"]', 'admin@finpilot.ai');
  await page.fill('input[name="password"]', 'w9MIquomakyemjLOzaOChA');
  await page.click('button[type="submit"]');
  await page.waitForURL('**/dashboard', { timeout: 15000 });
  console.log('已登录\n');

  let pass = 0, fail = 0;
  const startTime = Date.now();

  for (const task of TASKS) {
    const ok = await runTask(page, task);
    if (ok) pass++; else fail++;
  }

  const elapsed = Math.round((Date.now() - startTime) / 1000);
  await browser.close();

  console.log('\n═══════════════════════════════════════');
  console.log(`  压力测试完成: ${pass}✅ / ${fail}❌ (${elapsed}s)`);
  console.log('═══════════════════════════════════════');
}

main().catch(e => { console.error('FATAL:', e.message); process.exit(1); });
