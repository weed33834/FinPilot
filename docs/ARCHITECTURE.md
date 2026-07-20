# FinPilot AI 架构文档

本文档描述 FinPilot AI 的整体架构、核心子系统、数据流与设计决策。

## 三层架构

```
┌─────────────────────────────────────────────────────────┐
│                     接入层 (Frontend)                     │
│  React 19 + Vite SPA                                    │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐    │
│  │ AgentChatPage│ │ Admin Pages  │ │ Reports Page │    │
│  │  + Slash     │ │  + LLM Mgmt  │ │  + Approvals │    │
│  │  + Error Bar │ │  + Audit Log │ │              │    │
│  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘    │
│         │  SSE / REST    │  REST          │  REST       │
└─────────┼────────────────┼────────────────┼────────────┘
          ▼                ▼                ▼
┌─────────────────────────────────────────────────────────┐
│                     服务层 (Backend)                     │
│  FastAPI + LangGraph                                     │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐    │
│  │ Agent Router │ │ Auth Router  │ │ Admin Router │    │
│  │  - SSE stream│ │  - Session   │ │  - Users     │    │
│  │  - ReAct     │ │  - 2FA TOTP  │ │  - Audit Log │    │
│  └──────┬───────┘ └──────────────┘ └──────────────┘    │
│         │                                                │
│  ┌──────▼──────────────────────────────────────────┐   │
│  │        LangGraph ReAct 智能体运行时              │   │
│  │  agent → [should_continue] → tools → agent...    │   │
│  │                    └─ finalize → END             │   │
│  └──────┬──────────────────────────────────────────┘   │
│         │                                                │
│  ┌──────▼──────┐ ┌──────────────┐ ┌──────────────┐    │
│  │ LLM Client  │ │ Parser       │ │ RAG Engine   │    │
│  │ (多供应商)  │ │ (PDF/DOCX/...)│ │ (BM25+Vector)│    │
│  └─────────────┘ └──────────────┘ └──────────────┘    │
└─────────┬───────────────────────────────────────────────┘
          ▼
┌─────────────────────────────────────────────────────────┐
│                     数据层 (Data)                        │
│  SQLite / PostgreSQL │ 向量库 │ BM25 倒排 │ 文件存储    │
└─────────────────────────────────────────────────────────┘
```

## 核心子系统

### 1. 智能体运行时（LangGraph ReAct）

**位置**：`finpilot/agent/`

ReAct（Reasoning + Acting）循环是 FinPilot 的核心推理引擎：

```
START → agent → [should_continue] ─ tools → agent (循环)
                       └─ end → finalize → END
```

**关键文件**：

| 文件 | 职责 |
| :--- | :--- |
| `graph.py` | 图构建 + `run_agent` 入口 + `make_thread_id` |
| `react_nodes.py` | agent/tools/finalize/should_continue 节点 + ReAct 输出解析器 |
| `checkpoint.py` | 检查点后端（memory / sqlite） |
| `tools/` | 内置工具（nl2sql / document_qa / parse_document） |
| `state.py` | AgentState TypedDict 定义 |

**ReAct 输出解析器**（`parse_react_output`）支持三种 LLM 输出格式：

1. **标准 ReAct 三段式**：
   ```
   Thought: 我需要查询数据
   Action: nl2sql
   Action Input: {"question": "本月营业收入"}
   ```
2. **`<tool_call>` XML 风格**（Qwen / Mistral 系）：
   ```
   <tool_call>
   <function=nl2sql>
   <parameter=question>查询本月营业收入</parameter>
   </function>
   </tool_call>
   ```
3. **`<answer>` 标签**（部分模型直接给答案）：
   ```
   <answer>本月营业收入 100 万</answer>
   ```

**降级路径**：LLM 不可用（无配置 / 调用失败 / 演示模式）时，`_degrade_to_rule` 按 intent 直接调用对应工具给出答案，不阻断主流程。

**最大轮数**：5 轮工具调用（`MAX_REACT_STEPS = 5`），超出后强制 finalize。

### 2. SSE 流式聊天

**位置**：`finpilot/api/agent.py`

`/api/v1/agent/chat/stream` 端点用 `agent.stream(stream_mode="updates")` 替代 `agent.invoke()`，实现实时推送：

```python
for chunk in agent.stream(initial_state, config=config, stream_mode="updates"):
    for node_name, state_update in chunk.items():
        if node_name == "agent":
            yield _sse("thinking_token", {"content": f"💭 {thought}\n"})
            yield _sse("thinking_token", {"content": f"🔧 调用工具：{action}\n"})
        elif node_name == "tools":
            yield _sse("thinking_token", {"content": f"📋 结果：{observation[:200]}\n"})
        elif node_name == "finalize":
            final_state = {**final_state, **state_update}
```

**心跳保护**：15s 无事件时推送 `…\n`，防止前端误判超时。

**事件类型**：
- `start` — 携带 conversation_id
- `thinking_token` — ReAct 思考步骤增量
- `answer_token` — 最终答案分块（12 字/帧）
- `done` — 完成，携带 react_steps 与 confidence
- `error` — 服务端错误

### 3. 斜杠命令系统

**位置**：`frontend/src/utils/slashCommands.ts` + `frontend/src/components/SlashCommandPalette.tsx`

对话界面作为控制中枢，19 条命令按角色过滤：

| 分类 | 命令数 | 角色 |
| :--- | :--- | :--- |
| help | 1 | 所有用户 |
| data | 4 | user |
| report | 3 | user |
| analysis | 2 | user |
| system | 4 | admin |
| admin | 5 | admin |

**权限模型**：
- 前端 `getCommandsForRole(role)` 按角色过滤可见命令
- 后端 `require_admin` 依赖对所有 admin 命令的端点二次校验
- 前端过滤仅作 UX 优化，不构成安全边界

**命令解析**：`parseSlashCommand(raw, role)` 支持多词命令名（如 `/reports generate`），最后一个参数吃掉剩余值支持带空格的值（如 `/reports generate 600519 贵州茅台`）。

### 4. 错误系统

**位置**：`frontend/src/utils/errors.ts`

**FetchError 类**：携带 `status`/`url`/`method`/`bodyText`/`code`，让 fetch（非 axios）调用的 SSE 端点也能复用统一错误系统。

**错误级别**（`getErrorLevel`）：
- `network` — 无 HTTP 响应（超时、DNS、CORS、连接拒绝）
- `auth` — 401/403
- `client` — 4xx（除 401/403）
- `server` — 5xx
- `unknown` — 兜底

**错误格式**（`getErrorMessage`）：
```
[METHOD /url] STATUS 标签 — 后端 detail
[network] 请求超时（30s）— 后端未在规定时间内响应
```

**UI 呈现**（`index.css` `.chat-error-bar`）：
- 5 个 level 配色（server=红、auth=黄、client=橙、network=灰、unknown=红）
- 脉冲动画 + 光晕 + 渐变背景 + 左侧色条
- 入场动画（slide-in + pulse 2 次后停止）

### 5. LLM 多供应商配置

**位置**：`finpilot/llm/`

**配置优先级**：
1. 数据库（`llm_providers` + `llm_models` 表，管理后台维护）
2. 环境变量（`OPENAI_*` / `ANTHROPIC_*`）
3. 代码内默认值

**缓存**：60 秒 TTL 模块级缓存（`_cache` dict），供应商变更时通过 `invalidate_cache()` 主动清空。

**ModelRouter**：按问题复杂度路由模型档位（low/medium/high），简单问题用低成本模型，复杂问题用高性能模型。

**已测试供应商**：
- OpenAI（gpt-4o-mini）
- Anthropic（claude-3-5-sonnet）
- MoonWeaver（api.587.lol，OpenAI 兼容协议，moonweaver-4.8）
- Ollama（本地部署）

### 6. 文档解析与 RAG

**位置**：`finpilot/parser/` + `finpilot/rag/`

**多格式解析器**：
- PDF：pdfplumber + pypdfium2
- DOCX：python-docx
- Excel：openpyxl + pandas
- CSV：pandas

**RAG 检索**：
- BM25 倒排（rank-bm25）
- 向量检索
- RRF（Reciprocal Rank Fusion）融合两路结果

### 7. 安全合规

**位置**：`finpilot/security/`

- ABAC（Attribute-Based Access Control）访问控制
- TOTP 双因子认证（pyotp）
- PII 脱敏
- SQL 注入防护
- 审计日志（所有敏感操作留痕）

## 数据流

### 用户提问 → 答案（SSE 流式）

```
用户在 AgentChatPage 输入问题
  ↓
前端 fetch POST /api/v1/agent/chat/stream
  ↓
后端 event_generator()
  ├─ yield start (conversation_id)
  ├─ classify_intent + extract_parameters
  ├─ build_agent(tenant_id, user_id, db)
  ├─ for chunk in agent.stream(initial_state, stream_mode="updates"):
  │    ├─ agent 节点 → yield thinking_token (💭 thought + 🔧 action)
  │    ├─ tools 节点 → yield thinking_token (📋 observation)
  │    └─ finalize 节点 → 收集 final_state
  ├─ for chunk in answer: yield answer_token (12 字/帧)
  ├─ crud.add_message(assistant, answer)
  └─ yield done (react_steps, confidence)
  ↓
前端累积 thinking + answer，显示流式光标
  ↓
done 事件 → 关闭流式光标，显示推理链与置信度
```

### 斜杠命令执行

```
用户输入 /reports generate 600519 贵州茅台
  ↓
handleSubmit 检测到 / 开头 → 调用 executeSlashCommand
  ↓
parseSlashCommand(raw, role)
  ├─ 匹配命令名 "reports generate"
  ├─ 提取参数 ["600519", "贵州茅台"]
  └─ 返回 {command, args}
  ↓
command.handler(args) → 调用 api.post('/reports/generate', {...)
  ↓
后端创建异步任务，返回 task_id
  ↓
前端把结果渲染为 Markdown 表格插入对话流
```

## 设计决策

### 为什么用 LangGraph 而非直接调 LLM？

- **可观测性**：每个节点（agent/tools/finalize）的状态可流式推送，用户看到 ReAct 思考步骤
- **可恢复**：MemorySaver / SQLite 检查点支持会话持久化，中断后可续
- **可编排**：图结构清晰表达 "agent → tools → agent" 循环，便于扩展多智能体
- **降级路径**：LLM 不可用时按 intent 直接调工具，不阻断主流程

### 为什么用 SSE 而非 WebSocket？

- **单向流**：只需服务端推送，无需客户端双向消息
- **HTTP 兼容**：标准 HTTP，无需协议升级，Nginx/CDN 友好
- **自动重连**：浏览器原生支持 EventSource 重连
- **简化部署**：无需 WebSocket 负载均衡配置

### 为什么前端用自实现 MarkdownRenderer 而非 react-markdown？

- **无新增依赖**：项目未安装 react-markdown / remark / rehype，避免 React 19 peer 风险
- **XSS 防护**：HTML 转义 + DOMPurify 二次清洗
- **代码高亮**：内置轻量语法高亮（python / sql / json / js / bash）
- **表格支持**：GFM 管道表格，含对齐
- **代码块复制**：事件委托，无需每块单独绑定

### 为什么错误系统用 FetchError 而非 axios？

- **SSE 端点用 fetch**：流式响应需要 ReadableStream，axios 不支持
- **统一错误处理**：FetchError 模拟 AxiosError 的字段（status/url/method），让 `getErrorMessage` 统一处理两类错误
- **级别化高亮**：`getErrorLevel` 自动从 FetchError / AxiosError / DOMException / TypeError 推断级别

## 扩展点

### 添加新工具

1. 在 `finpilot/agent/tools/` 创建工具函数，用 `@tool_registry.register` 注册
2. 工具签名：`def my_tool(ctx: ToolContext, **params) -> dict`
3. 工具会自动出现在 ReAct 系统提示词的可用工具列表中

### 添加新斜杠命令

1. 在 `frontend/src/utils/slashCommands.ts` 的 `COMMANDS` 数组添加命令定义
2. 指定 `role: 'admin' | 'user'`、`category`、`name`、`usage`、`description`、`handler`
3. handler 调用 `api` 或 `adminApi`，用 `unwrap()` 提取 data，用 `renderTable()` 渲染 Markdown 表格
4. 命令自动出现在 `/help` 列表与 SlashCommandPalette 面板

### 添加新 LLM 供应商

1. 在管理后台 → LLM 供应商页面创建（provider_type 选 openai/anthropic/ollama）
2. 或通过 API `POST /api/v1/llm-providers` 创建
3. 自定义协议需在 `finpilot/llm/client.py` 的 `LLMClient.chat()` 中添加分支
