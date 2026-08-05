<div align="center">
  <img src="docs/banner.svg" alt="FinPilot" width="720" />
</div>

<div align="center">

# FinPilot · 企业级 AI 财务分析平台

**面向企业的开源 AI 财务分析平台**

[![License](https://img.shields.io/badge/license-MIT-1E5BFF.svg?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%20–%203.13-3776AB.svg?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688.svg?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB.svg?style=flat-square&logo=react&logoColor=white)](https://react.dev/)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.x-1C3C3C.svg?style=flat-square)](https://github.com/langchain-ai/langgraph)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-1E5BFF.svg?style=flat-square)](CONTRIBUTING.md)

**用自然语言查询财务数据，得到可计算、可追溯、可审计的结果。**

[快速开始](#快速开始) · [核心能力](#核心能力) · [产品展示](#产品展示) · [核心优势](#核心优势) · [技术栈](#技术栈) · [路线图](#路线图) · [贡献指南](#贡献指南)

</div>

[English](README.md) · **中文** · [日本語](README.ja.md)

---

## 产品概述

FinPilot 是一个开源、面向企业级的 AI 财务分析平台。平台通过结构化智能体（Agent）流水线，将大语言模型与您的财务数据连接，帮助财务团队实现：

- **自然语言数据查询** — 将自然语言问题翻译为 SQL，并在数据库中真实执行；
- **报告自动生成** — 基于模板生成分析报告，支持订阅推送与审批流程；
- **文档智能问答** — 基于 RAG 的 Excel / PDF / CSV / DOCX 文档问答；
- **财务建模** — DCF、DDM、LBO、WACC、可比公司、蒙特卡洛模拟，全部基于确定性代码计算。

所有输出**由代码计算、由模型解读**，并保留完整运行日志，支持全程追溯与审计。

---

## 核心能力

| 模块 | 能力说明 |
| :--- | :--- |
| 🤖 对话式问答 | 聊天中直接上传 Excel/PDF/CSV/DOCX，SSE 流式输出，实时展示推理步骤 |
| 📊 财务建模 | DCF · DDM · LBO · WACC · 可比公司 · 蒙特卡洛——确定性纯 Python 计算器 |
| 📑 报告中心 | 模板化报告、订阅推送、审批流程 |
| 🔍 RAG 文档问答 | BM25 + 向量 + RRF 融合检索，多格式文档解析 |
| 🛡 安全与合规 | ABAC 访问控制、TOTP 两步验证、PII 脱敏、注入防护、审计日志、角色分级 |
| 📡 运行日志 | 实时监控：日志 / 问答回放 / 模块状态 / 统计 |
| 🧰 可扩展性 | 工具 · 技能 · MCP 服务器 · 代码沙箱 · 提示词管理 |
| 💬 对话即控制台 | 斜杠指令、按角色过滤，可在对话中管理整个系统 |
| 📱 移动端优先 | 响应式移动端界面，桌面页面优雅降级 |
| 🚨 精准错误处理 | 分层错误系统（网络/认证/客户端/服务端），提供可操作的诊断信息 |

---

## 产品展示

**产品演示（5:21，无旁白）：** 视频内容来自真实运行环境——真实登录、真实大模型调用、真实 SQL 查询真实数据库。

<video controls src="docs/media/finpilot_demo.mp4" width="100%"></video>

<sub>[⬇ 下载 mp4](docs/media/finpilot_demo.mp4)（若页面不支持内嵌播放）</sub>

| 登录 | 数据看板 |
|:---:|:---:|
| ![登录](docs/screenshots/00-login-filled.png) | ![看板](docs/screenshots/dashboard.png) |

| 对话问答 | NL2SQL 查询结果 |
|:---:|:---:|
| ![对话](docs/screenshots/agent-answer.png) | ![查询](docs/screenshots/queries-result.png) |

| AI 生成报告 | 文档管理 |
|:---:|:---:|
| ![报告](docs/screenshots/reports-generated.png) | ![文档](docs/screenshots/documents.png) |

| 安全中心（2FA 设置） | 系统设置 |
|:---:|:---:|
| ![安全](docs/screenshots/security-2fa-setup.png) | ![设置](docs/screenshots/admin_settings.png) |

| 模型供应商（如阿里云百炼） | MCP 服务器 |
|:---:|:---:|
| ![模型](docs/screenshots/llm-providers.png) | ![MCP](docs/screenshots/admin_mcp-servers.png) |

---

## 核心优势

1. **计算而非生成。** DCF、WACC、回测、财务比率等计算全部基于确定性代码；模型负责解读结果，而非编造数字。
2. **全程可追溯。** 每一次 API 调用、每一轮问答、每个模块操作均记录于运行日志，支持逐步回放与审计。
3. **对话即控制台。** 输入 `/` 调出按角色过滤的指令面板，管理员可在对话中管理整个系统；普通用户仅能访问权限范围内的功能。

其他企业级特性：RAG 文档问答（BM25 + 向量 + RRF 融合）、Excel/PDF/DOCX 解析、ABAC 访问控制、TOTP 两步验证、移动端适配，以及可精准定位故障层级的分层错误系统。

---

## 快速开始

```bash
git clone https://github.com/weed33834/FinPilot.git   # 或下文任一镜像
cd FinPilot

# 后端
python3 -m venv venv && source venv/bin/activate
pip install -e .
cp .env.example .env        # 配置 LLM API Key
uvicorn finpilot.api.router:app --host 0.0.0.0 --port 8001

# 前端
cd frontend && npm install && npm run dev
```

打开 `http://localhost:5173`，使用 `.env` 中自动创建的 `FINPILOT_ADMIN_EMAIL` / `FINPILOT_ADMIN_PASSWORD` 登录，即可开始查询。

> 模型供应商在 **管理 → 模型供应商** 中配置（存储于数据库，环境变量兜底）。支持任意 OpenAI 兼容接口——阿里云百炼、DeepSeek、智谱等。

Docker 部署：`docker compose up -d`（Redis + PostgreSQL + 后端 + 前端）。详见 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)。

---

## 技术栈

Python 3.10–3.13 · FastAPI · LangGraph · SQLAlchemy · Pydantic · React 19 · Vite · TypeScript · Tailwind 4 · Zustand · Recharts · i18next · pdfplumber · openpyxl · BM25 · SQLite/PostgreSQL · Redis · Docker

---

## 路线图

- ✅ **v1/v2** — 对话问答、RAG、运行日志、报告与审批、安全基线、斜杠命令、财务校验引擎、多智能体辩论、回测与因子挖掘、MCP/技能/工具管理、i18n（中/英）、移动端适配
- 🚧 **v2.1** — 实时行情、知识图谱融合、企业 SSO

详细变更见 [CHANGELOG.md](CHANGELOG.md)。

---

## 贡献指南

欢迎提交 Issue 与 Pull Request——请先参阅 [CONTRIBUTING.md](CONTRIBUTING.md)。安全问题请通过 [SECURITY.md](SECURITY.md) 报告，请勿在公开 Issue 中披露。

---

## 三平台镜像

同一代码库在三平台同步维护，可按需选择访问。

| 平台 | 地址 |
|------|------|
| **GitHub** | https://github.com/weed33834/FinPilot |
| **GitCode** | https://gitcode.com/badhope/FinPilot |
| **Gitee** | https://gitee.com/badhope/FinPilot |

---

## License

基于 MIT 协议开源，见 [LICENSE](LICENSE)。

> **免责声明：** 本项目仅供学习与研究用途，不构成任何投资建议。
