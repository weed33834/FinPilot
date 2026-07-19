<div align="center">
  <a href="https://gitcode.com/badhope/FinPilot">
    <img src="docs/logo.svg" width="128" alt="FinPilot AI Logo" />
  </a>
  <h1>FinPilot AI</h1>
  <p><strong>面向企业财务场景的智能体平台 · 自主推理 · 全链路可观测</strong></p>
  <p>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-1E5BFF.svg?style=flat-square" alt="License: MIT" /></a>
    <img src="https://img.shields.io/badge/python-3.10+-3776AB.svg?style=flat-square" alt="Python" />
    <img src="https://img.shields.io/badge/FastAPI-0.115+-009688.svg?style=flat-square" alt="FastAPI" />
    <img src="https://img.shields.io/badge/React-19-61DAFB.svg?style=flat-square" alt="React 19" />
    <img src="https://img.shields.io/badge/TypeScript-5.x-3178C6.svg?style=flat-square" alt="TypeScript" />
    <img src="https://img.shields.io/badge/Tailwind-4-38BDF8.svg?style=flat-square" alt="Tailwind 4" />
    <img src="https://img.shields.io/badge/version-1.0.0-brightgreen.svg?style=flat-square" alt="Version" />
    <img src="https://img.shields.io/badge/platform-Linux%20%7C%20macOS%20%7C%20Windows-lightgrey.svg?style=flat-square" alt="Platform" />
  </p>
  <p>
    <a href="#快速开始">快速开始</a> ·
    <a href="#核心能力">核心能力</a> ·
    <a href="#架构概览">架构概览</a> ·
    <a href="#技术栈">技术栈</a> ·
    <a href="#项目结构">项目结构</a> ·
    <a href="#路线图">路线图</a>
  </p>
</div>

---

## 设计理念

FinPilot AI 把企业财务团队的真实工作流抽象成「**感知 → 推理 → 行动 → 留痕**」四段闭环：

- 由 LangGraph 编排的多角色智能体承担分析、建模、辩论、综合等任务；
- 财务计算严格走确定性代码路径（DCF、WACC、可比公司、回测），LLM 只负责叙事与解释；
- 每一次 API 调用、每一次问答、每一个模块开关都会写入运行记录，全程可回溯、可审计。

> **数字由代码计算，叙事由模型生成，每一行输出都能溯源。**

## 核心能力

| 模块 | 关键能力 |
| :--- | :--- |
| 🤖 **智能问答** | 对话式上传 Excel / PDF / CSV / DOCX，自动解析注入上下文，SSE 流式响应 |
| 📊 **财务建模** | DCF、DDM、LBO、WACC、可比公司、蒙特卡洛，纯 Python 计算算子 |
| 📑 **报告中心** | 报告模板、订阅推送、审批工作流，结构化研究输出 |
| 🔍 **文档解析** | 多格式解析器（PDF / DOCX / Excel / CSV）+ RAG 检索（BM25 + 向量 + RRF 融合） |
| 🛡 **安全合规** | ABAC 访问控制、TOTP 双因子、PII 脱敏、注入防护、审计日志 |
| 📡 **运行记录** | 日志列表 / 问答交互 / 模块状态 / 统计看板四 Tab 实时监测 |
| 🧰 **扩展体系** | 工具、技能、MCP 服务器、代码沙箱、提示词管理统一接入 |

## 架构概览

<div align="center">
  <img src="docs/architecture.svg" alt="FinPilot AI 系统架构" width="860" />
</div>

整体分为三层：

- **接入层** — React 19 + Vite SPA，对话 / 报告 / 审计 / 管理多面板，实时 SSE 推送
- **服务层** — FastAPI + PydanticAI，路由 / 鉴权 / 智能体编排 / 解析 / 检索 / 计算 / 留痕
- **数据层** — SQLite（ORM）、向量库、BM25 倒排、文件与配置存储

## 技术栈

| 类别 | 选型 |
| :--- | :--- |
| 后端 | Python 3.10+、FastAPI、PydanticAI、LangGraph、SQLAlchemy |
| 前端 | React 19、Vite、TypeScript、Tailwind 4、Zustand、Recharts、i18next |
| 文档与检索 | pdfplumber、python-docx、openpyxl、pandas、BM25、向量检索、RRF 融合 |
| 数据 | SQLite、向量存储 |
| 部署 | Docker、Uvicorn |

## 快速开始

### 1. 克隆仓库

```bash
git clone https://gitcode.com/badhope/FinPilot.git
cd FinPilot
```

### 2. 准备 Python 环境

```bash
python3 -m venv venv
source venv/bin/activate
pip install -e .
```

### 3. 配置 LLM 与数据源密钥

FinPilot AI 的 LLM 配置优先从数据库读取（在管理后台 → LLM 供应商页面维护），环境变量作为回退。

如果暂未配置数据库供应商，可直接设置环境变量：

```bash
export OPENAI_API_KEY="sk-..."
# 可选：
export OPENAI_BASE_URL="https://api.openai.com/v1"
export OPENAI_MODEL="gpt-4o-mini"
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

浏览器访问 `http://localhost:5173`，使用默认管理员账号登录即可。

### 6. 容器化部署（可选）

```bash
docker build -t finpilot-ai:1.0.0 .
docker run -d \
  -p 8001:8001 \
  -e OPENAI_API_KEY="sk-..." \
  --name finpilot finpilot-ai:1.0.0
```

## 项目结构

```
FinPilot AI
├── finpilot/                 # 后端业务包
│   ├── agent/                # 多智能体运行时（LangGraph 编排）
│   ├── api/                  # FastAPI 路由（auth / agent / admin / runtime-logs / ...）
│   ├── database/             # ORM 模型与 CRUD
│   ├── llm/                  # LLM 客户端与意图路由
│   ├── parser/               # 多格式文档解析器（PDF / DOCX / Excel / CSV）
│   ├── rag/                  # 检索增强（BM25 + 向量 + RRF 融合）
│   ├── security/             # ABAC / TOTP / PII / 审计 / 注入防护
│   ├── services/             # 业务服务（估值 / 回测 / 沙箱 / 运行记录 / ...）
│   ├── text2sql/             # 自然语言转 SQL
│   └── utils/                # 通用工具
├── finpilot_equity/          # Web 应用入口包
│   └── web_app/              # FastAPI 应用装配（路由挂载 / CORS / DB 初始化）
├── frontend/                 # React + Vite SPA
│   └── src/                  # 页面 / 组件 / API 客户端 / i18n / 状态
├── docs/                     # 项目标识图与架构图
├── Dockerfile                # 容器构建定义
├── setup.py                  # Python 包定义
├── requirements.txt          # Python 依赖
├── requirements-equity.txt   # Web 应用最小依赖
└── README.md
```

## 运行记录模块

设置板块内置「运行记录」模块，提供对全流程运行状态的实时监测：

| Tab | 用途 |
| :--- | :--- |
| **统计看板** | 总日志数、今日新增、成功率、模块启用状态聚合 |
| **日志列表** | 每次 API 调用的类别 / 级别 / 来源 / 耗时 / 状态码 / Payload 详情 |
| **问答交互** | 会话维度聚合，回放用户问题与智能体回答 |
| **模块状态** | LLM / 工具 / 技能 / 沙箱 / MCP / RAG / Text2SQL 等模块的启用统计 |

日志写入采用 best-effort 模式，记录失败不影响主流程；可一键导出 CSV 供离线分析。

## 路线图

- ✅ **v1.0.0** — 智能问答、文档解析、运行记录、报告与审批、安全合规基线
- 🚧 **v1.1.0** — 多智能体辩论编排、报告订阅调度、企业级 SSO
- 📌 **v1.2.0** — 实时行情接入、量化回测增强、知识图谱融合

## 协议

本项目基于 [MIT License](LICENSE) 开源，版权归 FinPilot AI 项目组所有，与其他外部项目无任何关联。

---

> **免责声明**：本项目代码与文档仅供学习研究使用，不应被视为金融建议或交易推荐。实际交易或投资前请咨询合格的专业人士。
