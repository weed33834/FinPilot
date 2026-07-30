import { chromium } from 'playwright'

const BASE = process.env.BASE || 'http://localhost:5174'
const OUT = '/workspace/mobile-shots'

// ---------- Mock data ----------
const now = Date.now()
const iso = (offsetMin = 0) => new Date(now - offsetMin * 60000).toISOString()

const dashboardSummary = {
  greeting: '下午好',
  report_count: 128,
  pending_approval_count: 3,
  document_count: 47,
  today_query_count: 19,
  recent_reports: [
    { id: 'rep-1', title: '2024 Q3 财务分析报告', status: 'approved', created_at: iso(30) },
    { id: 'rep-2', title: '现金流压力测试', status: 'reviewing', created_at: iso(120) },
    { id: 'rep-3', title: '同业对标分析', status: 'processing', created_at: iso(220) },
  ],
  recent_documents: [
    { id: 'doc-1', filename: '年报_2023.pdf', status: 'success', created_at: iso(15) },
    { id: 'doc-2', filename: '招股说明书.pdf', status: 'needs_review', created_at: iso(90) },
    { id: 'doc-3', filename: '审计报告.pdf', status: 'failed', created_at: iso(300) },
  ],
  report_status_distribution: { approved: 64, reviewing: 18, processing: 22, rejected: 9, draft: 15 },
  document_status_distribution: { success: 30, processing: 6, needs_review: 5, failed: 4, pending: 2 },
  recent_activities: [
    { id: 'a1', action: 'report.approve', resource: '2024 Q3 财务分析报告', result: 'success', created_at: iso(12) },
    { id: 'a2', action: 'document.parse.success', resource: '年报_2023.pdf', result: 'success', created_at: iso(40) },
    { id: 'a3', action: 'agent.query', resource: '上季度营收对比', result: 'success', created_at: iso(70) },
  ],
  approval_trend: [
    { date: '07-24', count: 4 }, { date: '07-25', count: 6 }, { date: '07-26', count: 3 },
    { date: '07-27', count: 8 }, { date: '07-28', count: 5 }, { date: '07-29', count: 7 },
  ],
}

const documents = [
  { id: 'doc-1', filename: '年报_2023.pdf', status: 'success', created_at: iso(15), confidence: 0.96 },
  { id: 'doc-2', filename: '招股说明书.pdf', status: 'needs_review', created_at: iso(90), confidence: 0.81 },
  { id: 'doc-3', filename: '审计报告.pdf', status: 'failed', created_at: iso(300) },
  { id: 'doc-4', filename: '季度财报_Q2.xlsx', status: 'processing', created_at: iso(45) },
  { id: 'doc-5', filename: '银行流水_2024.csv', status: 'pending', created_at: iso(5) },
]

const docDetail = {
  id: 'doc-1',
  filename: '年报_2023.pdf',
  status: 'success',
  confidence: 0.96,
  created_at: iso(15),
  parse_result: {
    company: '示例科技股份有限公司',
    period: '2023-01-01 ~ 2023-12-31',
    revenue: 1245000000,
    net_profit: 873000000,
    pages: 218,
  },
}

const reports = [
  { id: 'rep-1', title: '2024 Q3 财务分析报告', status: 'approved', created_at: iso(30) },
  { id: 'rep-2', title: '现金流压力测试', status: 'reviewing', created_at: iso(120) },
  { id: 'rep-3', title: '同业对标分析', status: 'processing', created_at: iso(220) },
  { id: 'rep-4', title: '估值模型 V2', status: 'rejected', created_at: iso(400) },
  { id: 'rep-5', title: '敏感性分析草稿', status: 'draft', created_at: iso(10) },
]

const reportDetail = {
  id: 'rep-1',
  title: '2024 Q3 财务分析报告',
  status: 'approved',
  summary: '本季度营收同比增长 12.4%，净利润提升 8.7%，资产负债率维持在健康区间，经营性现金流显著改善。',
  content: {
    title: '核心财务指标',
    sections: [
      { name: '营收(亿)', value: 124.5 },
      { name: '净利润(亿)', value: 87.3 },
      { name: '毛利率(%)', value: 42.3 },
      { name: '资产负债率(%)', value: 31.2 },
      { name: '经营现金流(亿)', value: 56.8 },
      { name: '结论', value: '整体稳健，建议关注应收账款周转' },
    ],
  },
}

const approvalsHistory = [
  { id: 'h1', report_id: 'rep-old-1', reviewer_id: 'u2', action: 'approve', comments: '数据核实无误', created_at: iso(600) },
  { id: 'h2', report_id: 'rep-old-2', reviewer_id: 'u2', action: 'reject', comments: '口径不一致', created_at: iso(900) },
  { id: 'h3', report_id: 'rep-old-3', reviewer_id: 'u3', action: 'modify', comments: '已退回修改', created_at: iso(1200) },
]

const hitlStats = { total: 12, pending: 4, approved: 6, rejected: 2, high_risk_pending: 2 }

const hitlRequests = [
  {
    id: 'h-1', action_type: 'delete_report', description: '删除已归档的过期季度报告 rep-arch-7',
    risk_level: 'high', action_params: { report_id: 'rep-arch-7', reason: '过期归档' },
    status: 'pending', created_at: iso(20), requested_by: 'agent-01',
  },
  {
    id: 'h-2', action_type: 'send_email', description: '向 12 位合伙人发送 Q3 业绩简报',
    risk_level: 'medium', action_params: { recipients: 12, template: 'q3_brief' },
    status: 'pending', created_at: iso(50), requested_by: 'agent-02',
  },
  {
    id: 'h-3', action_type: 'update_config', description: '调整风险阈值参数 risk_threshold=0.85',
    risk_level: 'low', action_params: { key: 'risk_threshold', value: 0.85 },
    status: 'pending', created_at: iso(80),
  },
  {
    id: 'h-4', action_type: 'export_data', description: '导出全量交易流水（已审批）',
    risk_level: 'medium', action_params: { scope: 'all' },
    status: 'approved', created_at: iso(200), resolved_by: 'admin', comment: '允许导出',
  },
]

const hitlDetail = {
  ...hitlRequests[0],
  resolved_at: null,
  context: { conversation_id: 'conv-x', step: 3 },
}

const SSE_BODY = [
  'data: {"type":"start","conversation_id":"conv-001"}',
  '',
  'data: {"type":"thinking_token","content":"正在检索最新季度财报与同业数据，并构建对比分析框架……"}',
  '',
  'data: {"type":"answer_token","content":"根据 **2024 Q3** 财报，公司营收同比增长 **12.4%**，净利润提升 **8.7%**。"}',
  '',
  'data: {"type":"answer_token","content":"经营性现金流改善明显，资产负债率维持在 31.2% 的健康区间。"}',
  '',
  'data: {"type":"done","thinking_time_ms":1480}',
  '',
].join('\n')

// ---------- Route handler ----------
function json(body, status = 200) {
  return {
    status,
    contentType: 'application/json',
    headers: { 'access-control-allow-origin': '*' },
    body: JSON.stringify(body),
  }
}

async function handleApi(route, request) {
  const url = new URL(request.url())
  const p = url.pathname
  const method = request.method()
  const q = url.searchParams

  // SSE stream for agent chat
  if (method === 'POST' && p.endsWith('/agent/chat/stream')) {
    return route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      headers: { 'cache-control': 'no-cache', connection: 'keep-alive' },
      body: SSE_BODY,
    })
  }

  // Auth
  if (p === '/api/v1/auth/me') return route.fulfill(json({ data: { role: 'admin', username: 'demo', id: 'u1' } }))
  if (p === '/api/v1/auth/2fa/status') return route.fulfill(json({ data: { enabled: true, setup_in_progress: false } }))
  if (p.startsWith('/api/v1/auth/2fa')) return route.fulfill(json({ data: { backup_codes: ['ABCD-1234', 'EFGH-5678', 'IJKL-9012'] } }))
  if (p === '/api/v1/auth/change-password') return route.fulfill(json({ data: {} }))

  // Notifications (must not 401 -> would log out)
  if (p === '/api/v1/notifications') return route.fulfill(json({ data: { items: [] } }))

  // Dashboard
  if (p === '/api/v1/dashboard/summary') return route.fulfill(json({ data: dashboardSummary }))

  // Documents
  if (/^\/api\/v1\/documents\/[^/]+$/.test(p)) return route.fulfill(json({ data: docDetail }))
  if (p === '/api/v1/documents') return route.fulfill(json({ data: { items: documents } }))

  // Reports
  if (/^\/api\/v1\/reports\/[^/]+\/export$/.test(p)) return route.fulfill(json({ data: { content_url: 'about:blank' } }))
  if (/^\/api\/v1\/reports\/[^/]+$/.test(p)) return route.fulfill(json({ data: reportDetail }))
  if (p === '/api/v1/reports') return route.fulfill(json({ data: { items: reports } }))

  // Approvals
  if (/^\/api\/v1\/approvals\/[^/]+\/action$/.test(p)) return route.fulfill(json({ data: {} }))
  if (p === '/api/v1/approvals') return route.fulfill(json({ data: approvalsHistory }))

  // HITL
  if (p === '/api/v1/hitl/stats') return route.fulfill(json({ code: 0, message: '', data: hitlStats }))
  if (/^\/api\/v1\/hitl\/[^/]+$/.test(p)) return route.fulfill(json({ code: 0, message: '', data: hitlDetail }))
  if (p === '/api/v1/hitl') return route.fulfill(json({ code: 0, message: '', data: hitlRequests }))

  // Fallback: empty 200 to avoid hard failures
  return route.fulfill(json({ data: {} }))
}

// ---------- Shooter ----------
const shots = [
  { path: '/dashboard', file: '01-dashboard', full: true },
  { path: '/documents', file: '02-documents', full: true },
  { path: '/documents/doc-1', file: '03-document-detail', full: true },
  { path: '/reports', file: '04-reports', full: true },
  { path: '/reports/rep-1', file: '05-report-detail', full: true },
  { path: '/approvals', file: '06-approvals', full: true },
  { path: '/hitl', file: '07-hitl', full: true },
  { path: '/security', file: '08-security', full: true },
  { path: '/audit', file: '09-desktop-required', full: true },
]

const run = async () => {
  const browser = await chromium.launch()
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
    isMobile: true,
    hasTouch: true,
    locale: 'zh-CN',
  })
  const page = await context.newPage()
  await page.route('**/api/v1/**', handleApi)

  // Capture console errors for later review
  const errors = []
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()) })
  page.on('pageerror', (e) => errors.push('PAGEERROR: ' + e.message))

  for (const s of shots) {
    await page.goto(BASE + s.path, { waitUntil: 'networkidle' })
    await page.waitForSelector('.mobile-shell', { timeout: 15000 })
    await page.waitForTimeout(400)
    await page.screenshot({ path: `${OUT}/${s.file}.png`, fullPage: s.full })
    console.log('shot', s.file)
  }

  // Agent chat — empty state
  await page.goto(BASE + '/agent', { waitUntil: 'networkidle' })
  await page.waitForSelector('.mobile-shell', { timeout: 15000 })
  await page.waitForTimeout(400)
  await page.screenshot({ path: `${OUT}/10-agent-empty.png`, fullPage: false })
  console.log('shot 10-agent-empty')

  // Agent chat — streamed conversation
  await page.fill('.mchat__input', '上季度营收对比一下')
  await page.click('.mchat__send')
  await page.waitForSelector('.mchat__bubble:has-text("营收")', { timeout: 15000 })
  await page.waitForTimeout(600)
  await page.screenshot({ path: `${OUT}/11-agent-stream.png`, fullPage: false })
  console.log('shot 11-agent-stream')

  await browser.close()

  console.log('\n=== Console errors (' + errors.length + ') ===')
  for (const e of errors.slice(0, 40)) console.log(' -', e)
}

run().catch((e) => { console.error(e); process.exit(1) })
