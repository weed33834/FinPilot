# FinPilot AI API 文档

本文档列出 FinPilot AI 后端暴露的主要 REST API 端点。所有端点均挂载在 `/api/v1` 前缀下（由 `finpilot/api/router.py` 聚合）。

运行时可通过 FastAPI 自动生成的交互式文档查看完整 schema：
- Swagger UI：`http://localhost:8001/docs`
- ReDoc：`http://localhost:8001/redoc`
- OpenAPI JSON：`http://localhost:8001/openapi.json`

## 认证

除少数公开端点外，所有 API 均需通过会话 Cookie 认证。

| 端点 | 方法 | 鉴权 | 说明 |
| :--- | :--- | :--- | :--- |
| `/api/v1/auth/login` | POST | 公开 | 邮箱+密码登录，成功后下发 `session_id` Cookie |
| `/api/v1/auth/logout` | POST | 已登录 | 注销当前会话 |
| `/api/v1/auth/me` | GET | 已登录 | 获取当前用户信息（含 `role` 字段：admin/user） |
| `/api/v1/auth/2fa/*` | * | 已登录 | TOTP 双因子启用/验证/禁用 |

### 角色权限

- `get_current_user` 依赖：任意已登录用户可访问
- `require_admin` 依赖：仅 `role=admin` 用户可访问（用户管理、LLM 供应商、审计日志等）

## 智能体对话

| 端点 | 方法 | 鉴权 | 说明 |
| :--- | :--- | :--- | :--- |
| `/api/v1/agent/chat` | POST | 用户 | 同步调用智能体，返回完整答案 |
| `/api/v1/agent/chat/stream` | POST | 用户 | **SSE 流式响应**，实时推送 ReAct 思考步骤与答案 token |
| `/api/v1/agent/conversations` | GET | 用户 | 列出当前用户会话 |
| `/api/v1/agent/conversations` | POST | 用户 | 创建新会话 |
| `/api/v1/agent/conversations/{id}/messages` | GET | 用户 | 获取会话消息历史 |

### SSE 事件类型（`/agent/chat/stream`）

```
data: {"type": "start", "question": "...", "conversation_id": "..."}
data: {"type": "thinking_token", "content": "💭 思考...\n"}
data: {"type": "thinking_token", "content": "🔧 调用工具：nl2sql\n"}
data: {"type": "thinking_token", "content": "📋 结果：...\n"}
data: {"type": "answer_token", "content": "本月营业收入..."}
data: {"type": "done", "thinking_time_ms": 12345, "payload": {"react_steps": [...], "confidence": 0.85}}
data: {"type": "error", "message": "..."}
```

### 心跳保护

长时间无事件时（>15s），后端推送 `data: {"type": "thinking_token", "content": "…\n"}` 防止前端误判超时。

## LLM 供应商管理（管理员）

| 端点 | 方法 | 鉴权 | 说明 |
| :--- | :--- | :--- | :--- |
| `/api/v1/llm-providers` | GET | admin | 列出所有供应商（分页） |
| `/api/v1/llm-providers` | POST | admin | 创建供应商（支持一并创建模型） |
| `/api/v1/llm-providers/{id}` | PUT | admin | 更新供应商 |
| `/api/v1/llm-providers/{id}` | DELETE | admin | 删除供应商（级联删除模型） |
| `/api/v1/llm-providers/{id}/test` | POST | admin | 测试供应商连通性 |
| `/api/v1/llm-providers/{provider_id}/models` | GET | admin | 列出该供应商下所有模型 |
| `/api/v1/llm-providers/{provider_id}/models` | POST | admin | 在该供应商下创建模型 |
| `/api/v1/llm-providers/models/{model_id}` | PUT | admin | 更新模型 |
| `/api/v1/llm-providers/models/{model_id}` | DELETE | admin | 删除模型 |

### 推荐配置：MoonWeaver

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

> 注：MoonWeaver API 当前仅提供 `moonweaver-4.8` 一个模型，可同时挂到 high/low 两个 tier；以往文档中的 `moonweaver-4.8-mini` 已被上游下线。

## 管理后台（管理员）

| 端点 | 方法 | 鉴权 | 说明 |
| :--- | :--- | :--- | :--- |
| `/api/v1/admin/dashboard` | GET | admin | 仪表盘聚合统计 |
| `/api/v1/admin/system/health` | GET | admin | 系统健康检查 |
| `/api/v1/admin/users` | GET | admin | 用户列表 |
| `/api/v1/admin/users/{id}` | PUT | admin | 更新用户（角色/状态） |
| `/api/v1/admin/audit-logs` | GET | admin | 审计日志列表 |
| `/api/v1/admin/approvals` | GET | admin | 待审批列表 |
| `/api/v1/admin/approvals/{id}` | POST | admin | 审批操作（approve/reject） |

## 用户功能

| 端点 | 方法 | 鉴权 | 说明 |
| :--- | :--- | :--- | :--- |
| `/api/v1/queries/nl2sql` | POST | 用户 | 自然语言转 SQL 并执行 |
| `/api/v1/queries/history` | GET | 用户 | 查询历史 |
| `/api/v1/documents` | GET | 用户 | 文档列表 |
| `/api/v1/documents/upload` | POST | 用户 | 上传文档（多格式） |
| `/api/v1/reports` | GET | 用户 | 报告列表 |
| `/api/v1/reports/generate` | POST | 用户 | 生成报告（异步任务） |
| `/api/v1/reports/{task_id}/status` | GET | 用户 | 报告生成状态 |
| `/api/v1/factor/categories` | GET | 用户 | 因子分类 |
| `/api/v1/backtest/strategies` | GET | 用户 | 回测策略列表 |

## 运行记录

| 端点 | 方法 | 鉴权 | 说明 |
| :--- | :--- | :--- | :--- |
| `/api/v1/runtime-logs` | GET | admin | 日志列表（支持筛选） |
| `/api/v1/runtime-logs/stats` | GET | admin | 统计看板数据 |
| `/api/v1/runtime-logs/export` | GET | admin | 导出 CSV |
| `/api/v1/runtime-logs/modules` | GET | admin | 模块启用状态 |

## 响应包装

所有业务端点统一返回 `{code, message, data}` 包装格式：

```json
{
  "code": 0,
  "message": "success",
  "data": { ... }
}
```

- `code=0` 表示成功，非 0 表示业务错误
- HTTP 状态码仍按 RESTful 约定（200/400/401/403/404/422/500）
- 错误响应体形如 `{"detail": "..."}`（FastAPI 默认）或 `{"code": N, "message": "..."}`

## 错误处理

前端 `errors.ts` 中的 `FetchError` 与 `getErrorMessage()` 会把后端错误转换为带来源标签的精确字符串，例如：

```
[POST /agent/chat/stream] 500 服务器内部错误 — KeyError: 'react_steps'
[network] 请求超时（30s）— 后端未在规定时间内响应
[GET /queries/nl2sql] 422 参数校验失败 — body.question: field required
```

详见 README 的「错误系统」章节。
