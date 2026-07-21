"""调试脚本：登录后访问 /agent 页面，dump 关键 DOM 元素，确认 selector 准确性。"""
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=['--no-sandbox'])
    page = b.new_page()

    # 监听所有 API 请求
    def on_response(resp):
        if '/api/v1/' in resp.url:
            print(f"  [resp] {resp.status} {resp.url}")
    page.on('response', on_response)

    page.goto('http://localhost:5173/login', wait_until='networkidle')
    print("=== Login page ===")
    print("URL:", page.url)

    # 填写登录表单
    page.query_selector('input[name="username"]').fill('admin@finpilot.ai')
    page.query_selector('input[type="password"]').fill('admin123')

    # 点击登录
    print("\n=== 点击登录 ===")
    page.query_selector('button[type="submit"]').click()
    page.wait_for_timeout(3000)
    print("点击后 URL:", page.url)
    print("页面错误提示:", page.query_selector('.alert-error') and page.query_selector('.alert-error').inner_text())

    # 直接访问 /agent
    print("\n=== 访问 /agent ===")
    page.goto('http://localhost:5173/agent', wait_until='networkidle')
    print("URL:", page.url)
    page.wait_for_selector('input.chat-input-field', timeout=8000)
    print("找到 chat-input-field ✓")

    b.close()
