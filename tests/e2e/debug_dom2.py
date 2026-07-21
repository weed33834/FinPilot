"""检查登录后页面 DOM，确认 sidebar / nav / KPI 元素。"""
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=['--no-sandbox'])
    page = b.new_page()
    page.goto('http://localhost:5173/login', wait_until='networkidle')
    page.fill('input[name="username"]', 'admin@finpilot.ai')
    page.fill('input[type="password"]', 'admin123')
    page.click('button[type="submit"]')
    page.wait_for_timeout(3000)
    print("登录后 URL:", page.url)
    print("\n=== Dashboard DOM ===")
    # 找 sidebar 相关
    for sel in ['nav', 'aside', '.sidebar', '.layout-sidebar', '.sidebar-toggle',
                'header', '.topbar', '[role="navigation"]', 'main', '.layout']:
        els = page.query_selector_all(sel)
        if els:
            print(f"  {sel}: {len(els)} 个")
    print("\n=== 找带 sidebar 的 class ===")
    els = page.query_selector_all('[class*="sidebar"], [class*="nav"], [class*="layout"]')
    for el in els[:15]:
        cls = el.get_attribute('class') or ''
        tag = el.evaluate('e=>e.tagName')
        print(f"  <{tag}> class={cls[:100]}")

    print("\n=== KPI 页面 ===")
    page.goto('http://localhost:5173/kpi', wait_until='networkidle')
    page.wait_for_timeout(2000)
    # 找 data-testid
    els = page.query_selector_all('[data-testid]')
    print(f"data-testid 元素数: {len(els)}")
    for el in els[:10]:
        print(f"  data-testid={el.get_attribute('data-testid')!r} tag={el.evaluate('e=>e.tagName')}")
    # 找 button
    btns = page.query_selector_all('button')
    print(f"\nbutton 数: {len(btns)}")
    for btn in btns[:10]:
        text = btn.inner_text()[:30]
        tid = btn.get_attribute('data-testid')
        cls = (btn.get_attribute('class') or '')[:50]
        print(f"  button text={text!r} data-testid={tid!r} class={cls}")
    # 截图
    page.screenshot(path='/workspace/FinPilot/tests/e2e/screenshots/debug_kpi.png', full_page=True)
    b.close()
