# FinPilot AI 部署指南

本文档覆�?FinPilot AI 的本地开发、Docker 容器化、生产部署三种场景�?

## 前置要求

| 组件 | 版本 | 说明 |
| :--- | :--- | :--- |
| Python | 3.10 �?3.13 | 推荐 3.11 �?3.12；低�?3.10 或等�?3.14 不支�?|
| Node.js | 18+ | 前端构建；推�?20 LTS |
| npm | 9+ | �?Node 安装 |
| Docker（可选） | 24+ | 容器化部�?|
| Git | 2.30+ | 克隆仓库 |

## 一、本地开发部�?

### 1. 克隆仓库

```bash
git clone https://gitcode.com/badhope/FinPilot.git
cd FinPilot
```

### 2. 准备 Python 环境

推荐使用 venv �?pyenv 隔离环境�?

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -e .
```

> 若系统默�?Python 不是 3.10�?.13，可�?[pyenv](https://github.com/pyenv/pyenv) 切换�?
> ```bash
> pyenv install 3.11.15
> pyenv local 3.11.15
> python -m venv venv
> ```

### 3. 配置环境变量

```bash
cp .env.example .env
# 按需编辑 .env，至少配置一�?LLM 供应�?
```

最小配置示例：

```bash
# .env
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
```

完整环境变量清单�?[`.env.example`](../.env.example)�?

### 4. 启动后端

```bash
uvicorn finpilot_equity.web_app.main:app --host 0.0.0.0 --port 8001 --reload
```

首次启动会：
- 在工作目录创�?`finpilot.db`（SQLite�?
- 初始化数据库 schema
- 创建默认管理�?`admin@finpilot.ai` / `admin123`

验证启动成功�?
```bash
curl http://localhost:8001/api/v1/auth/me
# 应返�?401（未登录），说明服务已起�?
```

### 5. 启动前端

```bash
cd frontend
npm install
npm run dev
```

浏览器访�?`http://localhost:5173`，使用默认管理员账号登录�?

> Vite dev server 会自动代�?`/api/v1` �?`http://localhost:8001`（见 `vite.config.ts`）�?

### 6. 配置 LLM 供应商（推荐�?

登录后进入「管理后�?�?LLM 供应商」页面，创建供应商。推荐使�?MoonWeaver（OpenAI 兼容协议）：

| 字段 | �?|
| :--- | :--- |
| name | MoonWeaver |
| provider_type | openai |
| base_url | https://api.587.lol/v1 |
| api_key | any |
| is_default | �?|
| models | moonweaver-4.8（API 当前仅有此一个模型，可同时挂�?high/low tier�?|

也可通过 API 创建�?
```bash
curl -b cookies.txt -X POST http://localhost:8001/api/v1/llm-providers \
  -H "Content-Type: application/json" \
  -d '{"name":"MoonWeaver","provider_type":"openai","base_url":"https://api.587.lol/v1","api_key":"any","is_default":true,"models":[{"model_name":"moonweaver-4.8","tier":"high"}]}'
```

## 二、Docker 容器化部�?

### 1. 构建镜像

```bash
docker build -t finpilot-ai:1.0.0 .
```

镜像基于 `python:3.13-slim`，安装完�?`requirements.txt` + `pip install -e .`，暴露端�?8001�?

### 2. 运行容器

```bash
docker run -d \
  --name finpilot \
  -p 8001:8001 \
  --env-file .env \
  -v finpilot-data:/app/data \
  finpilot-ai:1.0.0
```

| 参数 | 说明 |
| :--- | :--- |
| `-p 8001:8001` | 映射后端端口 |
| `--env-file .env` | 注入环境变量 |
| `-v finpilot-data:/app/data` | 持久�?SQLite 数据库与上传文件（可选） |

### 3. 验证容器

```bash
docker logs -f finpilot
curl http://localhost:8001/api/v1/auth/me   # 应返�?401
```

### 4. 前端单独部署

前端可单独构建为静态资源，�?Nginx �?CDN 托管�?

```bash
cd frontend
npm run build        # 产物�?frontend/dist/
```

�?`dist/` 部署到任意静态服务器，配置反向代理将 `/api/v1` 转发到后端容器�?

## 三、生产部署建�?

### 反向代理（Nginx 示例�?

```nginx
server {
    listen 80;
    server_name finpilot.example.com;

    # 前端静态资�?
    location / {
        root /var/www/finpilot-frontend;
        try_files $uri /index.html;
    }

    # 后端 API 反向代理
    location /api/v1/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE 流式响应需�?
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
    }
}
```

### 数据库持久化

默认 SQLite（`finpilot.db`），适合开发与小规模部署。生产环境建议切�?PostgreSQL�?

1. 修改 `finpilot/database/session.py` 中的连接字符�?
2. �?`.env` 中设�?`DATABASE_URL=postgresql+pg8000://user:pass@host:5432/finpilot`
3. 重启服务，schema 会自动创�?

### 进程管理

推荐�?systemd �?supervisor 管理 uvicorn 进程�?

```ini
# /etc/systemd/system/finpilot.service
[Unit]
Description=FinPilot AI Backend
After=network.target

[Service]
User=finpilot
WorkingDirectory=/opt/finpilot
EnvironmentFile=/opt/finpilot/.env
ExecStart=/opt/finpilot/venv/bin/uvicorn finpilot_equity.web_app.main:app --host 0.0.0.0 --port 8001
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable finpilot
sudo systemctl start finpilot
```

### 安全清单

- [ ] 修改默认管理员密码（`admin123` �?强密码）
- [ ] 启用 HTTPS（Let's Encrypt 或商业证书）
- [ ] 配置 `FINPILOT_ADMIN_EMAILS` 限制管理员白名单
- [ ] 启用 TOTP 双因子认证（用户中心 �?安全设置�?
- [ ] 定期备份 `finpilot.db` �?PostgreSQL
- [ ] 审查审计日志（管理后�?�?审计日志�?
- [ ] 限制服务器出站访问（仅允�?LLM API 域名�?

## 四、故障排�?

### 后端启动失败

| 错误 | 原因 | 解决 |
| :--- | :--- | :--- |
| `ModuleNotFoundError: No module named 'fastapi'` | 依赖未安�?| `pip install -e .` |
| `ImportError: cannot import name 'create_router'` | 未安装本�?| `pip install -e .` |
| `PermissionError: finpilot.db` | 工作目录不可�?| 改用有写权限的目�?|
| `pg8000.Error` | PostgreSQL 连接失败 | 检�?`DATABASE_URL` 与网�?|

### 前端构建失败

| 错误 | 原因 | 解决 |
| :--- | :--- | :--- |
| `Cannot find module 'react'` | node_modules 未安�?| `npm install` |
| TypeScript 报错 | 类型错误 | `npx tsc --noEmit` 查看详情 |
| Vite 代理 404 | 后端未启�?| 先启动后�?`:8001` |

### SSE 流式响应卡住

- 检�?Nginx 是否关闭�?`proxy_buffering`
- 检�?`proxy_read_timeout` 是否足够长（建议 �?00s�?
- 后端日志查看是否�?`agent.stream()` 循环�?
- LLM 调用慢（MoonWeaver 单次 25-40s）属正常，前端会看到心跳 `…`

### LLM 调用失败

- 在管理后�?�?LLM 供应商页面点击「测试」按�?
- 检�?`api_key` 是否正确
- 检�?`base_url` 是否可达（`curl https://api.587.lol/v1/models`�?
- 查看后端日志�?`LLMUnavailableError` 详情
- 启用 `FINPILOT_LLM_DEMO_FALLBACK=1` 可在 LLM 不可用时降级为占位文本（仅开发环境）
