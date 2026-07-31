<div align="center">
  <img src="docs/banner.svg" alt="FinPilot AI" width="720" />
</div>

<div align="center">

# FinPilot AI

[English](README.md) | [中文](README.zh.md) | [日本語](README.ja.md)

**面向企业财务场景的智能体平台 · 自主推理 · 全链路可观测**

[![License](https://img.shields.io/badge/license-MIT-1E5BFF.svg?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-3776AB.svg?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688.svg?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB.svg?style=flat-square&logo=react&logoColor=white)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.x-3178C6.svg?style=flat-square&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Vite](https://img.shields.io/badge/Vite-8-646CFF.svg?style=flat-square&logo=vite&logoColor=white)](https://vitejs.dev/)
[![Tailwind](https://img.shields.io/badge/Tailwind-4-38BDF8.svg?style=flat-square&logo=tailwindcss&logoColor=white)](https://tailwindcss.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.x-1C3C3C.svg?style=flat-square)](https://github.com/langchain-ai/langgraph)
[![Version](https://img.shields.io/badge/version-1.0.0-brightgreen.svg?style=flat-square)](CHANGELOG.md)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-1E5BFF.svg?style=flat-square)](CONTRIBUTING.md)
[![Stars](https://img.shields.io/badge/all%20contributors-welcome-3DDC97.svg?style=flat-square)](#贡献)

**智能体 · 财务建模 · 报告中心 · 安全合规 · 精细错误 · 对话即控制**

[快速开始](#快速开始) ·
[核心能力](#核心能力) ·
[架构概览](#架构概览) ·
[ReAct 工作流](#react-工作流) ·
[对话即控制中枢](#对话即控制中枢) ·
[错误系统](#错误系统) ·
[技术栈](#技术栈) ·
[项目结构](#项目结构) ·
[环境变量](#环境变量) ·
[路线图](#路线图) ·
[贡献](#贡献)

</div>

---

## 设计理念

FinPilot AI 将企业财务团队的真实工作流抽象为「**感知 → 推理 → 行动 → 留痕**」四段闭环：

- 由 **LangGraph** 编排的多角色智能体承担分析、建模、辩论与综合等任务；
- 财务计算走**确定性代码路径**（DCF、WACC、可比公司、回测），LLM 仅承担叙事与解释；
- 每次 API 调用、每次问答、每个模块开关都会写入**运行记录**，全程可回溯、可审计。

> 数字由代码计算，叙事由模型生成，每一行输出均可溯源。

---

## 核心能力

| 模块 | 关键能力 |
| :--- | :--- |
| 🤖 **智能问答** | 对话式上传 Excel / PDF / CSV / DOCX，自动解析并注入上下文，**SSE 流式响应**实时推送 ReAct 思考步骤 |
| 📊 **财务建模** | DCF、DDM、LBO、WACC、可比公司、蒙特卡洛，均为纯 Python 计算算子 |
| 📑 **报告中心** | 报告模板、订阅推送、审批工作流，输出结构化研究成果 |
| 🔍 **文档解析** | 多格式解析器（PDF / DOCX / Excel / CSV）+ RAG 检索（BM25 + 向量 + RRF 融合） |
| 🛡 **安全合规** | ABAC 访问控制、TOTP 双因子、PII 脱敏、注入防护、审计日志、**角色分级权限** |
| 📡 **运行记录** | 日志列表 / 问答交互 / 模块状态 / 统计看板四 Tab 实时监测 |
| 🧰 **扩展体系** | 工具、技能、MCP 服务器、代码沙箱、提示词管理统一接入 |
| 💬 **对话即控制** | **斜杠命令系统**——在对话界面调用全部功能，按角色过滤权限 |
| 🚨 **精细化错误** | **FetchError + 级别化高亮**——网络 / 权限 / 请求 / 服务四色警示灯 |

---

## 架构概览

<div align="center">
  <img src="docs/architecture.svg" alt="FinPilot AI 系统架构" width="860" />
</div>

整体分为三层：

- **接入层** — React 19 + Vite SPA，对话 / 报告 / 审计 / 管理多面板，实时 SSE 推送。
  - `AgentChatPage` 集成斜杠命令面板、级别化错误条与流式思考步骤；
  - `MarkdownRenderer` 自带 XSS 清洗与代码块语法高亮；
  - `SlashCommandPalette` 提供模糊搜索、键盘导航与角色过滤。
- **服务层** — FastAPI + LangGraph，承担路由 / 鉴权 / 智能体编排 / 解析 / 检索 / 计算 / 留痕。
  - ReAct 智能体通过 `agent.stream(stream_mode="updates")` 实时推送每个节点状态；
  - 兼容多种 LLM 输出格式：标准 ReAct 三段式、`<tool_call>` XML、`<answer>` 标签；
  - LLM 配置优先从数据库读取（管理后台维护），环境变量作为回退。
- **数据层** — SQLite（ORM）、向量库、BM25 倒排、文件与配置存储。
  - ReAct 检查点支持 `memory`（默认）与 `sqlite`（持久化）两种后端。

---

## ReAct 工作流

<div align="center">
  <img src="docs/workflow.svg" alt="ReAct 工作流" width="860" />
</div>

ReAct 循环最多 5 轮工具调用，每个节点完成后通过 SSE 实时推送：

- **start** — 会话创建
- **thinking_token** — Agent 思考过程 / 工具调用 / Observation 结果
- **answer_token** — 最终回答增量
- **done** — 携带推理链、置信度、intent 的终态事件
- **error** — 异常事件（携带详细错误信息）

**心跳保护**：15 秒内无事件时推送 `…`，避免前端误判超时。

---

## 对话即控制中枢

对话界面是 FinPilot 的控制中枢——管理员可在对话框中通过斜杠命令调用全部功能，控制整个程序、应用与智能体；普通用户只能调用其权限范围内的命令。

### 斜杠命令面板

在对话框输入 `/` 即弹出命令面板，支持模糊搜索、键盘上下选择、按分类分组。所有命令按角色过滤：

| 分类 | 命令示例 | 角色 |
| :--- | :--- | :--- |
| **help** | `/help`、`/?` | 所有用户 |
| **data** | `/dashboard`、`/queries history`、`/conversations list`、`/documents list` | user |
| **report** | `/reports list`、`/reports generate 600519 贵州茅台`、`/reports status <task_id>` | user |
| **analysis** | `/factor categories`、`/backtest strategies` | user |
| **system** | `/admin status`、`/admin health`、`/models list`、`/models test <provider_id>` | admin |
| **admin** | `/users list`、`/audit logs`、`/approvals list`、`/templates list`、`/subscriptions list` | admin |

### 权限分级

- **管理员（admin）**：可调用全部 19 条命令，覆盖数据 / 研报 / 分析 / 系统 / 管理五大类。
- **普通用户（user）**：仅可调用 help + data + report + analysis 四类共 9 条命令，无法访问系统状态、用户管理、审计日志等敏感操作。
- 后端 `require_admin` 依赖对所有 admin 命令端点二次校验，前端过滤仅作 UX 优化。

---

## 错误系统

FinPilot 的错误系统追求**精准定位 + 醒目可见**，不再出现「操作失败，请稍后重试」这类零信息量的兜底。

### 错误级别与配色

每条错误按级别显示一盏不同颜色的「警示灯」，带脉冲动画、光晕与渐变背景，确保在深色 / 浅色主题下均清晰可见：

| 级别 | 颜色 | 触发场景 |
| :--- | :--- | :--- |
| `network` | 灰色 | 连接超时、DNS 失败、CORS 拒绝、后端未启动 |
| `auth` | 黄色 | 401 未登录、403 权限不足 |
| `client` | 橙色 | 400 / 404 / 422 请求参数错误、路由不存在 |
| `server` | 红色 | 500 / 502 / 503 服务器内部错误 |
| `unknown` | 红色 | 兜底未分类错误 |

### 错误信息格式

错误条会显示具体出错的接口、HTTP 方法、状态码与后端返回的 detail，例如：

```
[POST /agent/chat/stream] 500 服务器内部错误 — KeyError: 'react_steps'
[network] 请求超时（30s）— 后端未在规定时间内响应，可能是 LLM 推理过慢或后端阻塞
[GET /model-configs] 422 参数校验失败 — body.question: field required
```

### 实现要点

- `FetchError` 类：携带 `status` / `url` / `method` / `bodyText` / `code`，使 `fetch`（非 axios）调用的 SSE 端点也能复用统一错误系统；
- `getErrorLevel(err)`：从 FetchError / AxiosError / DOMException / TypeError 自动推断错误级别；
- `getErrorMessage(err)`：将原始错误转换为带来源标签、状态码与后端原因的精确字符串。

---

## 技术栈

| 类别 | 选型 |
| :--- | :--- |
| 后端 | Python 3.10–3.13、FastAPI、LangGraph、SQLAlchemy、Pydantic |
| 前端 | React 19、Vite、TypeScript、Tailwind 4、Zustand、Recharts、i18next |
| 文档与检索 | pdfplumber、python-docx、openpyxl、pandas、BM25、向量检索、RRF 融合 |
| 数据 | SQLite（默认）、PostgreSQL（生产可选） |
| 部署 | Docker、Uvicorn、Nginx（可选反向代理） |
| 安全 | ABAC、TOTP、PII 脱敏、注入防护、审计日志 |

---

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/weed33834/FinPilot.git
cd FinPilot
```

> GitCode 镜像：`git clone https://gitcode.com/badhope/FinPilot.git`

### 2. 准备 Python 环境

```bash
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -e .
```

> 需要 Python 3.10–3.13。推荐使用 [pyenv](https://github.com/pyenv/pyenv) 管理多版本。

### 3. 配置环境变量

复制示例文件并按需修改（所有变量均为可选）：

```bash
cp .env.example .env
```

最小配置只需设置 LLM 供应商。FinPilot 的 LLM 配置**优先从数据库读取**（在管理后台 → LLM 供应商页面维护），环境变量作为回退。

**方式 A：使用环境变量（快速试用）**

```bash
export OPENAI_API_KEY="sk-..."
# 可选：
export OPENAI_BASE_URL="https://api.openai.com/v1"
export OPENAI_MODEL="gpt-4o-mini"
```

**方式 B：使用 MoonWeaver（OpenAI 兼容协议）**

```bash
# 在管理后台 → LLM 供应商页面创建：
#   name=MoonWeaver, provider_type=openai, base_url=https://api.587.lol/v1
#   api_key=any, is_default=true
#   models: moonweaver-4.8（API 当前仅提供此模型，可同时挂到 high/low tier）
```

也支持 Anthropic：

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export ANTHROPIC_MODEL="claude-3-5-sonnet-20241022"
```

### 4. 启动后端

```bash
uvicorn finpilot_equity.web_app.main:app --host 0.0.0.0 --port 8001
```

首次启动会自动创建数据库并初始化默认管理员账号：

| 字段 | 值 |
| :--- | :--- |
| 用户名 | `admin@finpilot.ai` |
| 密码 | `admin123` |

> ⚠️ 首次登录后请立即在「用户管理」中修改默认密码。

### 5. 启动前端

```bash
cd frontend
npm install
npm run dev
```

浏览器访问 `http://localhost:5173`，使用默认管理员账号登录。

### 6. 容器化部署（可选）

```bash
docker build -t finpilot-ai:1.0.0 .
docker run -d \
  -p 8001:8001 \
  --env-file .env \
  --name finpilot finpilot-ai:1.0.0
```

详细部署指引见 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)。

---

## 项目结构

```
FinPilot AI
├── finpilot/                 # 后端业务包
│   ├── agent/                # 多智能体运行时（LangGraph 编排）
│   │   ├── graph.py          # ReAct 图构建 + run_agent 入口
│   │   ├── react_nodes.py    # agent/tools/finalize 节点 + 多格式解析器
│   │   ├── checkpoint.py     # 检查点后端（memory / sqlite）
│   │   └── tools/            # 内置工具（nl2sql / document_qa / parse_document）
│   ├── api/                  # FastAPI 路由
│   │   ├── router.py         # 聚合路由 + 默认管理员初始化
│   │   ├── agent.py          # SSE 流式聊天（agent.stream）
│   │   ├── compat.py         # 前端契约兼容层
│   │   ├── llm_providers.py  # LLM 供应商 CRUD
│   │   └── deps.py           # 鉴权依赖（require_admin / get_current_user）
│   ├── database/             # ORM 模型与 CRUD
│   ├── llm/                  # LLM 客户端 / 配置 / 模型路由
│   ├── parser/               # 多格式文档解析器（PDF / DOCX / Excel / CSV）
│   ├── rag/                  # 检索增强（BM25 + 向量 + RRF 融合）
│   ├── security/             # ABAC / TOTP / PII / 审计 / 注入防护
│   ├── services/             # 业务服务（估值 / 回测 / 沙箱 / 运行记录 / ...）
│   ├── text2sql/             # 自然语言转 SQL
│   └── utils/                # 通用工具
├── finpilot_equity/          # Web 应用入口包
│   └── web_app/              # FastAPI 应用装配（路由挂载 / CORS / DB 初始化）
├── frontend/                 # React + Vite SPA
│   └── src/
│       ├── pages/            # AgentChatPage / Admin / Reports / ...
│       ├── components/       # SlashCommandPalette / MarkdownRenderer / ReasoningChain / ...
│       ├── utils/            # errors.ts (FetchError) / slashCommands.ts / ...
│       ├── api/              # client.ts / adminClient.ts (axios 实例)
│       ├── stores/           # authStore (zustand, role 字段)
│       └── index.css         # 全局样式 + 错误条打灯高亮
├── docs/                     # 项目标识图、架构图、工作流图、API/架构/部署文档
├── .github/                  # Issue / PR 模板 + CI workflow
├── .env.example              # 环境变量示例
├── CHANGELOG.md              # 变更日志
├── CONTRIBUTING.md           # 贡献指引
├── SECURITY.md               # 安全策略
├── CODE_OF_CONDUCT.md        # 行为准则
├── Dockerfile                # 容器构建定义
├── setup.py                  # Python 包定义
├── requirements.txt          # Python 依赖
├── requirements-equity.txt   # Web 应用最小依赖
└── README.md
```

---

## 环境变量

完整的环境变量清单见 [`.env.example`](.env.example)。摘要：

| 变量 | 用途 | 默认值 |
| :--- | :--- | :--- |
| `FINPILOT_ADMIN_EMAIL` | 默认管理员邮箱 | `admin@finpilot.ai` |
| `FINPILOT_ADMIN_PASSWORD` | 默认管理员密码 | `admin123` |
| `FINPILOT_ADMIN_EMAILS` | 管理员邮箱白名单（逗号分隔） | `admin@finpilot.ai` |
| `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `OPENAI_MODEL` | OpenAI 供应商 | — |
| `ANTHROPIC_API_KEY` / `ANTHROPIC_BASE_URL` / `ANTHROPIC_MODEL` | Anthropic 供应商 | — |
| `FINPILOT_LLM_DEMO_FALLBACK` | LLM 不可用时是否启用演示降级 | 禁用 |
| `FINPILOT_CHECKPOINT_BACKEND` | ReAct 检查点后端（`memory` / `sqlite`） | `memory` |
| `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` / `GITHUB_REDIRECT_URI` | GitHub OAuth 登录 | 占位符 |

---

## 运行记录模块

设置板块内置「运行记录」模块，对全流程运行状态进行实时监测：

| Tab | 用途 |
| :--- | :--- |
| **统计看板** | 总日志数、今日新增、成功率、模块启用状态聚合 |
| **日志列表** | 每次 API 调用的类别 / 级别 / 来源 / 耗时 / 状态码 / Payload 详情 |
| **问答交互** | 会话维度聚合，回放用户问题与智能体回答 |
| **模块状态** | LLM / 工具 / 技能 / 沙箱 / MCP / RAG / Text2SQL 等模块的启用统计 |

日志写入采用 best-effort 模式，记录失败不影响主流程；可一键导出 CSV 供离线分析。

---

## 路线图

- ✅ **v1.0.0** — 智能问答、文档解析、运行记录、报告与审批、安全合规基线、斜杠命令系统、级别化错误系统、SSE 流式 ReAct 推送
- 🚧 **v1.1.0** — 多智能体辩论编排、报告订阅调度、企业级 SSO
- 📌 **v1.2.0** — 实时行情接入、量化回测增强、知识图谱融合

完整变更记录见 [CHANGELOG.md](CHANGELOG.md)。

---

## 贡献

欢迎提交 Issue 与 Pull Request。请先阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 了解开发约定与提交规范，行为规范参见 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。

报告安全漏洞请遵循 [SECURITY.md](SECURITY.md)，**请勿在公开 Issue 中披露安全漏洞**。

### 贡献者

<a href="https://github.com/weed33834/FinPilot/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=weed33834/FinPilot" alt="contributors" />
</a>

> GitCode 镜像：<https://gitcode.com/badhope/FinPilot>

---

## 许可证

本项目基于 [MIT License](LICENSE) 开源，版权归 FinPilot AI 项目组所有，与其他外部项目无任何关联。

---

> **免责声明**：本项目代码与文档仅供学习研究使用，不应被视为金融建议或交易推荐。实际交易或投资前请咨询合格的专业人士。
