"""单独测试 KPI 页面访问。"""
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=['--no-sandbox'])
    ctx = b.new_context()
    page = ctx.new_page()
    page.goto('http://localhost:5173/login', wait_until='networkidle')
    page.fill('input[name="username"]', 'admin@finpilot.ai')
    page.fill('input[type="password"]', 'admin123')
    page.click('button[type="submit"]')
    page.wait_for_timeout(3000)
    print("登录后 URL:", page.url)

    # 重新访问 /kpi
    print("\n=== 访问 /kpi ===")
    page.goto('http://localhost:5173/kpi', wait_until='networkidle')
    page.wait_for_timeout(5000)
    print("KPI URL:", page.url)
    print("Title:", page.title())
    body_text = page.inner_text('body')[:400]
    print("Body 前 400 字:", body_text)
    # 找 data-testid
    els = page.query_selector_all('[data-testid]')
    print(f"\ndata-testid 元素数: {len(els)}")
    for el in els[:10]:
        print(f"  data-testid={el.get_attribute('data-testid')!r}")
    page.screenshot(path='/workspace/FinPilot/tests/e2e/screenshots/debug_kpi2.png', full_page=True)
    b.close()
