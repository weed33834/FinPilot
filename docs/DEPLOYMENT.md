# FinPilot AI — Deployment Guide

This document covers three scenarios for FinPilot AI: local development, Docker containerization, and production deployment.

## Prerequisites

| Component | Version | Notes |
| :--- | :--- | :--- |
| Python | 3.10 – 3.13 | 3.11 or 3.12 recommended; below 3.10 or equal to 3.14 is unsupported |
| Node.js | 18+ | for the frontend build; 20 LTS recommended |
| npm | 9+ | ships with Node |
| Docker (optional) | 24+ | for containerized deployment |
| Git | 2.30+ | to clone the repo |

## 1. Local Development

### 1. Clone the repository

```bash
git clone https://gitcode.com/badhope/FinPilot.git
cd FinPilot
```

### 2. Prepare the Python environment

A venv or pyenv is recommended:

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -e .
```

> If the system default Python is not 3.10–3.13, switch with [pyenv](https://github.com/pyenv/pyenv):
> ```bash
> pyenv install 3.11.15
> pyenv local 3.11.15
> python -m venv venv
> ```

### 3. Configure environment variables

```bash
cp .env.example .env
# edit .env as needed; configure at least one LLM provider
```

Minimal config example:

```bash
# .env
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
```

The full variable list is in [`.env.example`](../.env.example).

### 4. Start the backend

```bash
uvicorn finpilot_equity.web_app.main:app --host 0.0.0.0 --port 8001 --reload
```

On first start it will:
- create `finpilot.db` (SQLite) in the working directory
- initialize the database schema
- create the default admin **only if** `FINPILOT_ADMIN_EMAIL` + `FINPILOT_ADMIN_PASSWORD` are set (otherwise no default admin is created — register manually)

Verify it is up:
```bash
curl http://localhost:8001/api/v1/auth/me
# should return 401 (not logged in) — service is running
```

### 5. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` and log in with the default admin account.

> The Vite dev server auto-proxies `/api/v1` to `http://localhost:8001` (see `vite.config.ts`).

### 6. Configure an LLM provider (recommended)

After logging in, go to **Admin → LLM Providers** and create a provider. MoonWeaver (OpenAI-compatible) is recommended:

| Field | Value |
| :--- | :--- |
| name | MoonWeaver |
| provider_type | openai |
| base_url | https://api.587.lol/v1 |
| api_key | any |
| is_default | ✓ |
| models | moonweaver-4.8 (the API currently offers only this model; mount to both `high`/`low` tiers) |

Or create it via API:
```bash
curl -b cookies.txt -X POST http://localhost:8001/api/v1/llm-providers \
  -H "Content-Type: application/json" \
  -d '{"name":"MoonWeaver","provider_type":"openai","base_url":"https://api.587.lol/v1","api_key":"any","is_default":true,"models":[{"model_name":"moonweaver-4.8","tier":"high"}]}'
```

## 2. Docker Containerization

The repository ships a `docker-compose.yml` that orchestrates Redis + PostgreSQL + backend + frontend in one command — this is the **recommended** path.

### One-command stack (recommended)

```bash
cp .env.example .env          # set SECRET_KEY and FINPILOT_ADMIN_PASSWORD
docker compose up -d
docker compose logs -f backend
```

Service ports:

| Service | Port | Notes |
| :--- | :--- | :--- |
| Frontend | `http://localhost:8080` | Nginx-served static build |
| Backend | `http://localhost:8010` | API + `/health` + `/metrics` |
| Redis | `6379` | session / rate-limit / lock |
| PostgreSQL | `5432` | primary database |

The backend `/health/ready` endpoint is used by Compose / K8s `depends_on` for readiness.

### Manual image build & run (alternative)

```bash
docker build -t finpilot-ai:2.0.0 .
docker run -d \
  --name finpilot \
  -p 8001:8001 \
  --env-file .env \
  -v finpilot-data:/app/data \
  finpilot-ai:2.0.0
```

| Flag | Description |
| :--- | :--- |
| `-p 8001:8001` | map the backend port |
| `--env-file .env` | inject environment variables |
| `-v finpilot-data:/app/data` | persist SQLite DB and uploads (optional) |

### Frontend standalone build

The frontend can be built to static assets and served by Nginx or a CDN:

```bash
cd frontend
npm run build        # output in frontend/dist/
```

Deploy `dist/` to any static server and configure a reverse proxy to forward `/api/v1` to the backend container.

## 3. Production Recommendations

### Reverse proxy (Nginx example)

```nginx
server {
    listen 80;
    server_name finpilot.example.com;

    # Frontend static assets
    location / {
        root /var/www/finpilot-frontend;
        try_files $uri /index.html;
    }

    # Backend API reverse proxy
    location /api/v1/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Required for SSE streaming
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
    }
}
```

### Database persistence

Default is SQLite (`finpilot.db`), fine for development and small deployments. For production, switch to PostgreSQL:

1. Set `FINPILOT_DATABASE_URL=postgresql+pg8000://user:pass@host:5432/finpilot` in `.env` (the compose stack does this automatically).
2. Restart the service; the schema is created automatically.

### Process management

Manage the uvicorn process with systemd or supervisor:

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

### Security checklist

- [ ] Change the default admin password (use a strong one via `FINPILOT_ADMIN_PASSWORD`)
- [ ] Enable HTTPS (Let's Encrypt or a commercial cert)
- [ ] Restrict the admin whitelist with `FINPILOT_ADMIN_EMAILS`
- [ ] Enable TOTP 2FA (User Center → Security Settings)
- [ ] Back up `finpilot.db` or PostgreSQL regularly
- [ ] Review audit logs (Admin → Audit Logs)
- [ ] Limit the server's outbound access (only allow LLM API domains)

## 4. Troubleshooting

### Backend fails to start

| Error | Cause | Fix |
| :--- | :--- | :--- |
| `ModuleNotFoundError: No module named 'fastapi'` | deps not installed | `pip install -e .` |
| `ImportError: cannot import name 'create_router'` | package not installed | `pip install -e .` |
| `PermissionError: finpilot.db` | working dir not writable | use a writable directory |
| `psycopg.OperationalError` | PostgreSQL connection failed | check `FINPILOT_DATABASE_URL` and network |

### Frontend build fails

| Error | Cause | Fix |
| :--- | :--- | :--- |
| `Cannot find module 'react'` | node_modules missing | `npm install` |
| TypeScript error | type error | `npx tsc --noEmit` for details |
| Vite proxy 404 | backend not started | start backend on `:8001` first |

### SSE streaming stalls

- Check that Nginx has `proxy_buffering off`.
- Check `proxy_read_timeout` is long enough (≥300s recommended).
- Inspect backend logs to see if it is stuck in the `agent.stream()` loop.
- Slow LLM calls (MoonWeaver can take 25–40s per call) are normal; the frontend shows the `…` heartbeat.

### LLM call fails

- Click "Test" on the LLM Providers page in Admin.
- Verify `api_key` is correct.
- Verify `base_url` is reachable (`curl https://api.587.lol/v1/models`).
- Check backend logs for `LLMUnavailableError` details.
- Set `FINPILOT_LLM_DEMO_FALLBACK=1` to degrade to placeholder text when the LLM is unavailable (development only).
