# FinPilot AI — API Reference

This document lists the main REST API endpoints exposed by the FinPilot AI backend. All endpoints are mounted under the `/api/v1` prefix (aggregated by `finpilot/api/router.py`).

At runtime, the full schema is available via FastAPI's auto-generated interactive docs:
- Swagger UI: `http://localhost:8001/docs`
- ReDoc: `http://localhost:8001/redoc`
- OpenAPI JSON: `http://localhost:8001/openapi.json`

## Authentication

Except for a few public endpoints, all APIs require session-cookie authentication.

| Endpoint | Method | Auth | Description |
| :--- | :--- | :--- | :--- |
| `/api/v1/auth/login` | POST | Public | Email + password login; issues a `session_id` cookie on success |
| `/api/v1/auth/logout` | POST | Logged in | Log out the current session |
| `/api/v1/auth/me` | GET | Logged in | Get current user info (includes `role`: `admin`/`user`) |
| `/api/v1/auth/2fa/*` | * | Logged in | TOTP 2FA enable / verify / disable |

### Role permissions

- `get_current_user` dependency: any logged-in user can access.
- `require_admin` dependency: only `role=admin` users (user management, LLM providers, audit logs, etc.).

## Agent Chat

| Endpoint | Method | Auth | Description |
| :--- | :--- | :--- | :--- |
| `/api/v1/agent/chat` | POST | User | Synchronous agent call; returns the complete answer |
| `/api/v1/agent/chat/stream` | POST | User | **SSE streaming**; pushes ReAct reasoning steps and answer tokens in real time |
| `/api/v1/agent/conversations` | GET | User | List current user's conversations |
| `/api/v1/agent/conversations` | POST | User | Create a new conversation |
| `/api/v1/agent/conversations/{id}/messages` | GET | User | Get a conversation's message history |

### SSE event types (`/agent/chat/stream`)

```
data: {"type": "start", "question": "...", "conversation_id": "..."}
data: {"type": "thinking_token", "content": "💭 thinking...\n"}
data: {"type": "thinking_token", "content": "🔧 Calling tool: nl2sql\n"}
data: {"type": "thinking_token", "content": "📋 Result: ...\n"}
data: {"type": "answer_token", "content": "this month's revenue..."}
data: {"type": "done", "thinking_time_ms": 12345, "payload": {"react_steps": [...], "confidence": 0.85}}
data: {"type": "error", "message": "..."}
```

### Heartbeat protection

When no event arrives for a long time (>15s), the backend pushes `data: {"type": "thinking_token", "content": "…\n"}` to prevent the frontend from misjudging a timeout.

## LLM Provider Management (Admin)

| Endpoint | Method | Auth | Description |
| :--- | :--- | :--- | :--- |
| `/api/v1/llm-providers` | GET | admin | List all providers (paginated) |
| `/api/v1/llm-providers` | POST | admin | Create a provider (models can be created in the same call) |
| `/api/v1/llm-providers/{id}` | PUT | admin | Update a provider |
| `/api/v1/llm-providers/{id}` | DELETE | admin | Delete a provider (cascades to its models) |
| `/api/v1/llm-providers/{id}/test` | POST | admin | Test provider connectivity |
| `/api/v1/llm-providers/{provider_id}/models` | GET | admin | List models under this provider |
| `/api/v1/llm-providers/{provider_id}/models` | POST | admin | Create a model under this provider |
| `/api/v1/llm-providers/models/{model_id}` | PUT | admin | Update a model |
| `/api/v1/llm-providers/models/{model_id}` | DELETE | admin | Delete a model |

### Recommended config: MoonWeaver

```
POST /api/v1/llm-providers
{
  "name": "MoonWeaver",
  "provider_type": "openai",
  "base_url": "https://api.587.lol/v1",
  "api_key": "any",
  "is_default": true,
  "models": [
    {"model_name": "moonweaver-4.8", "display_name": "MoonWeaver 4.8", "tier": "high"},
    {"model_name": "moonweaver-4.8", "display_name": "MoonWeaver 4.8 (low tier)", "tier": "low"}
  ]
}
```

> Note: The MoonWeaver API currently provides only the `moonweaver-4.8` model, which can be mounted to both the `high` and `low` tiers. The older `moonweaver-4.8-mini` was retired upstream.

## Admin Panel (Admin)

| Endpoint | Method | Auth | Description |
| :--- | :--- | :--- | :--- |
| `/api/v1/admin/dashboard` | GET | admin | Aggregated dashboard statistics |
| `/api/v1/admin/system/health` | GET | admin | System health check |
| `/api/v1/admin/users` | GET | admin | User list |
| `/api/v1/admin/users/{id}` | PUT | admin | Update a user (role / status) |
| `/api/v1/admin/audit-logs` | GET | admin | Audit log list |
| `/api/v1/admin/approvals` | GET | admin | Pending-approval list |
| `/api/v1/admin/approvals/{id}` | POST | admin | Approval action (approve/reject) |

## User Features

| Endpoint | Method | Auth | Description |
| :--- | :--- | :--- | :--- |
| `/api/v1/queries/nl2sql` | POST | User | Natural language → SQL, then execute |
| `/api/v1/queries/history` | GET | User | Query history |
| `/api/v1/documents` | GET | User | Document list |
| `/api/v1/documents/upload` | POST | User | Upload a document (multi-format) |
| `/api/v1/reports` | GET | User | Report list |
| `/api/v1/reports/generate` | POST | User | Generate a report (async task) |
| `/api/v1/reports/{task_id}/status` | GET | User | Report generation status |
| `/api/v1/factor/categories` | GET | User | Factor categories |
| `/api/v1/backtest/strategies` | GET | User | Backtest strategy list |

## Run-Log

| Endpoint | Method | Auth | Description |
| :--- | :--- | :--- | :--- |
| `/api/v1/runtime-logs` | GET | admin | Log list (with filters) |
| `/api/v1/runtime-logs/stats` | GET | admin | Stats dashboard data |
| `/api/v1/runtime-logs/export` | GET | admin | Export CSV |
| `/api/v1/runtime-logs/modules` | GET | admin | Module enable-status |

## Response Envelope

All business endpoints return a unified `{code, message, data}` envelope:

```json
{
  "code": 0,
  "message": "success",
  "data": { }
}
```

- `code=0` means success; non-zero means a business error.
- HTTP status codes still follow REST conventions (200/400/401/403/404/422/500).
- Error bodies look like `{"detail": "..."}` (FastAPI default) or `{"code": N, "message": "..."}`.

## Error Handling

The frontend's `errors.ts` (`FetchError` + `getErrorMessage()`) converts backend errors into precise, source-tagged strings, e.g.:

```
[POST /agent/chat/stream] 500 Internal Server Error — KeyError: 'react_steps'
[network] Request timed out (30s) — backend did not respond in time
[GET /queries/nl2sql] 422 Validation failed — body.question: field required
```

See the "Error System" section of the README for details.
