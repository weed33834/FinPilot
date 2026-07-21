"""配置 hcnsec NewAPI channel 作为 LLM provider（包含 25 个模型）。"""
import requests

BASE = "http://localhost:8001/api/v1"

# 登录
login_resp = requests.post(
    f"{BASE}/auth/login",
    json={"username": "admin@finpilot.ai", "password": "admin123", "remember_me": False},
)
assert login_resp.status_code == 200, login_resp.text
token = login_resp.json()["data"]["access_token"]
headers = {"Authorization": f"Bearer {token}"}
print(f"[OK] 登录成功，token={token[:20]}...")

# 检查现有 providers
resp = requests.get(f"{BASE}/llm-providers", headers=headers)
print(f"[INFO] 现有 providers: {resp.json()['data']['total']} 个")

# hcnsec NewAPI channel 配置
HCNSEC_KEY = "sk-j4TEjjV0fKgqvliSXc8jko2EHzBmXnazsVaGCUa0sxSmZAH7"
HCNSEC_URL = "https://api.hcnsec.cn/v1"

# hcnsec 通常支持的 25 个模型（OpenAI 兼容协议）
MODELS = [
    # OpenAI 系列
    {"model_name": "gpt-4o", "display_name": "GPT-4o", "tier": "high", "is_active": True},
    {"model_name": "gpt-4o-mini", "display_name": "GPT-4o Mini", "tier": "low", "is_active": True},
    {"model_name": "gpt-4-turbo", "display_name": "GPT-4 Turbo", "tier": "high", "is_active": True},
    {"model_name": "gpt-3.5-turbo", "display_name": "GPT-3.5 Turbo", "tier": "low", "is_active": True},
    # Claude 系列
    {"model_name": "claude-3-5-sonnet-20241022", "display_name": "Claude 3.5 Sonnet", "tier": "high", "is_active": True},
    {"model_name": "claude-3-opus-20240229", "display_name": "Claude 3 Opus", "tier": "high", "is_active": True},
    {"model_name": "claude-3-haiku-20240307", "display_name": "Claude 3 Haiku", "tier": "low", "is_active": True},
    # 国产模型
    {"model_name": "glm-4-plus", "display_name": "智谱 GLM-4-Plus", "tier": "high", "is_active": True},
    {"model_name": "glm-4", "display_name": "智谱 GLM-4", "tier": "medium", "is_active": True},
    {"model_name": "glm-4-flash", "display_name": "智谱 GLM-4-Flash", "tier": "low", "is_active": True},
    {"model_name": "glm-4-air", "display_name": "智谱 GLM-4-Air", "tier": "medium", "is_active": True},
    {"model_name": "qwen-max", "display_name": "通义千问 Max", "tier": "high", "is_active": True},
    {"model_name": "qwen-plus", "display_name": "通义千问 Plus", "tier": "medium", "is_active": True},
    {"model_name": "qwen-turbo", "display_name": "通义千问 Turbo", "tier": "low", "is_active": True},
    {"model_name": "deepseek-chat", "display_name": "DeepSeek Chat", "tier": "medium", "is_active": True},
    {"model_name": "deepseek-coder", "display_name": "DeepSeek Coder", "tier": "medium", "is_active": True},
    {"model_name": "moonshot-v1-8k", "display_name": "Kimi 8K", "tier": "medium", "is_active": True},
    {"model_name": "moonshot-v1-32k", "display_name": "Kimi 32K", "tier": "medium", "is_active": True},
    {"model_name": "moonshot-v1-128k", "display_name": "Kimi 128K", "tier": "high", "is_active": True},
    {"model_name": "yi-large", "display_name": "零一万物 Yi-Large", "tier": "high", "is_active": True},
    {"model_name": "yi-medium", "display_name": "零一万物 Yi-Medium", "tier": "medium", "is_active": True},
    {"model_name": "baichuan2-13b", "display_name": "百川 Baichuan2-13B", "tier": "low", "is_active": True},
    {"model_name": "spark-v3.5", "display_name": "讯飞星火 v3.5", "tier": "medium", "is_active": True},
    {"model_name": "ernie-bot-4", "display_name": "文心一言 4.0", "tier": "high", "is_active": True},
    {"model_name": "ernie-bot-turbo", "display_name": "文心一言 Turbo", "tier": "low", "is_active": True},
]

# 检查是否已有 hcnsec provider
existing = resp.json()["data"]["items"]
hcnsec = next((p for p in existing if p["name"] == "hcnsec"), None)
if hcnsec:
    # 更新
    pid = hcnsec["id"]
    print(f"[INFO] 更新现有 hcnsec provider (id={pid})")
    resp = requests.put(
        f"{BASE}/llm-providers/{pid}",
        headers=headers,
        json={
            "name": "hcnsec",
            "provider_type": "openai",
            "base_url": HCNSEC_URL,
            "api_key": HCNSEC_KEY,
            "is_default": True,
            "is_active": True,
            "models": MODELS,
        },
    )
    print(f"[{'OK' if resp.status_code == 200 else 'FAIL'}] 更新: {resp.status_code} {resp.text[:200]}")
else:
    # 创建
    print(f"[INFO] 创建 hcnsec provider")
    resp = requests.post(
        f"{BASE}/llm-providers",
        headers=headers,
        json={
            "name": "hcnsec",
            "provider_type": "openai",
            "base_url": HCNSEC_URL,
            "api_key": HCNSEC_KEY,
            "is_default": True,
            "is_active": True,
            "models": MODELS,
        },
    )
    print(f"[{'OK' if resp.status_code == 200 else 'FAIL'}] 创建: {resp.status_code} {resp.text[:200]}")

# 列出确认
resp = requests.get(f"{BASE}/llm-providers", headers=headers)
providers = resp.json()["data"]["items"]
print(f"\n[INFO] 当前 providers ({len(providers)} 个):")
for p in providers:
    print(f"  - {p['name']} (default={p['is_default']}, type={p['provider_type']}, has_api_key={p['has_api_key']})")

# 测试 hcnsec 连通性（取一个 provider 的 id 来测试）
hcnsec = next((p for p in providers if p["name"] == "hcnsec"), None)
if hcnsec:
    pid = hcnsec["id"]
    print(f"\n[INFO] 测试 hcnsec 连通性 (id={pid})...")
    resp = requests.post(f"{BASE}/llm-providers/{pid}/test", headers=headers, timeout=30)
    print(f"  状态: {resp.status_code}")
    print(f"  响应: {resp.text[:300]}")
