<div align="center">
  <img src="docs/banner.svg" alt="FinPilot" width="720" />
</div>

<div align="center">

# FinPilot · 会算数的财务 AI 助手

**不是嘴上说说，是真去查、真去算、真出报告。**

[![License](https://img.shields.io/badge/license-MIT-1E5BFF.svg?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%20–%203.13-3776AB.svg?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688.svg?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB.svg?style=flat-square&logo=react&logoColor=white)](https://react.dev/)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.x-1C3C3C.svg?style=flat-square)](https://github.com/langchain-ai/langgraph)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-1E5BFF.svg?style=flat-square)](CONTRIBUTING.md)

[快速开始](#快速开始) · [实拍截图](#实拍截图) · [看家本领](#看家本领) · [技术栈](#技术栈) · [路线图](#路线图) · [一起搞](#一起搞)

</div>

[English](README.md) · **中文** · [日本語](README.ja.md)

---

## 先说实话：下面这些不是摆拍

见过太多"演示五分钟，背后全是假数据"的项目，所以我们把话放这儿：

- 查询截图里那条 SQL，是**真实模型生成**的，并且**真的在数据库里跑了一遍**；
- 报告里的分析文字，是**真实模型写的**，不是手打上去的；
- 图表里每一个数字，都是**代码算出来的**，模型只负责把话说圆。

> **数字是代码算的，话是模型写的，每一步都能查得到出处。**

---

## 这东西是干嘛的？

一句话：**你开口问，它真去算。**

上传一份财报，然后用大白话问它：

> "净利润最高的月份是哪个月？"

它会把你的话翻译成 SQL，真的去数据库里查，把结果表甩给你看，再让模型给你解读两句。想要报告？一句话的事——生成、订阅、审批一条龙。

说白了，FinPilot 想解决的是 AI 财务分析里最常见的尴尬：**模型说得头头是道，但数字全是一本正经地编**。我们让数字回归代码，让模型专心讲人话。

---

## 实拍截图

**实机演示（5:21，无旁白）：** 视频里的每一帧都来自真实运行——真实登录、真实大模型调用、真实 SQL 查真实数据库。

<video controls src="docs/media/finpilot_demo.mp4" width="100%"></video>

<sub>[⬇ 下载 mp4](docs/media/finpilot_demo.mp4)（若页面不支持内嵌播放）</sub>

| 登录 | 数据看板 |
|:---:|:---:|
| ![登录](docs/screenshots/00-login-filled.png) | ![看板](docs/screenshots/dashboard.png) |

| 智能对话（真实 AI 回答） | NL2SQL 真实查询结果 |
|:---:|:---:|
| ![对话](docs/screenshots/agent-answer.png) | ![查询](docs/screenshots/queries-result.png) |

| AI 生成报告 | 文档管理 |
|:---:|:---:|
| ![报告](docs/screenshots/reports-generated.png) | ![文档](docs/screenshots/documents.png) |

| 安全中心（2FA 设置） | 系统设置 |
|:---:|:---:|
| ![安全](docs/screenshots/security-2fa-setup.png) | ![设置](docs/screenshots/admin_settings.png) |

| 模型供应商（阿里云百炼等） | MCP 服务器 |
|:---:|:---:|
| ![模型](docs/screenshots/llm-providers.png) | ![MCP](docs/screenshots/admin_mcp-servers.png) |

---

## 看家本领

1. **数字是真的。** DCF、WACC、回测、比率……全部走确定性代码。模型只负责解释，不负责编数。
2. **全程可追溯。** 每一次 API 调用、每一轮问答、每个开关操作都进运行日志，agent 干了啥、为什么，都能回放。
3. **聊天框就是控制台。** 输入 `/` 弹出指令面板，按角色过滤——管理员在对话框里就能驱动整个系统，普通用户只能看到自己权限内的东西。

再加上这些"标配但做扎实"的：RAG 文档问答（BM25 + 向量 + RRF 融合）、Excel/PDF/DOCX 解析、ABAC 访问控制、TOTP 两步验证、移动端壳子，以及一个会明确告诉你**是哪一层炸了**的错误系统——而不是干巴巴一句"操作失败"。

---

## 快速开始

```bash
git clone https://github.com/weed33834/FinPilot.git   # 或下文任一镜像
cd FinPilot

# 后端
python3 -m venv venv && source venv/bin/activate
pip install -e .
cp .env.example .env        # 填上你的 LLM API Key
uvicorn finpilot.api.router:app --host 0.0.0.0 --port 8001

# 前端
cd frontend && npm install && npm run dev
```

打开 `http://localhost:5173`，用 `.env` 里的 `FINPILOT_ADMIN_EMAIL` / `FINPILOT_ADMIN_PASSWORD` 登录，就能开问。

> 模型供应商在 **管理 → 模型供应商** 里配（存数据库，环境变量兜底）。任何 OpenAI 兼容接口都能接——阿里云百炼、DeepSeek、智谱都行。

想上 Docker：`docker compose up -d`（Redis + PostgreSQL + 后端 + 前端）。详见 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)。

---

## 技术栈

Python 3.10–3.13 · FastAPI · LangGraph · SQLAlchemy · Pydantic · React 19 · Vite · TypeScript · Tailwind 4 · Zustand · Recharts · i18next · pdfplumber · openpyxl · BM25 · SQLite/PostgreSQL · Redis · Docker

---

## 路线图

- ✅ **v1/v2** — 对话问答、RAG、运行日志、报告与审批、安全基线、斜杠命令、财务校验引擎、多智能体辩论、回测与因子挖掘、MCP/技能/工具管理、i18n（中/英）、移动端适配
- 🚧 **v2.1** — 实时行情、知识图谱融合、企业 SSO

详细变更见 [CHANGELOG.md](CHANGELOG.md)。

---

## 一起搞

欢迎提 Issue 和 PR——先看 [CONTRIBUTING.md](CONTRIBUTING.md)。安全问题走 [SECURITY.md](SECURITY.md)，别在公开 Issue 里报。

---

## 三平台镜像

同一份代码，三个平台同步推送，哪个快用哪个。

| 平台 | 地址 |
|------|------|
| **GitHub** | https://github.com/weed33834/FinPilot |
| **GitCode** | https://gitcode.com/badhope/FinPilot |
| **Gitee** | https://gitee.com/badhope/FinPilot |

---

## License

MIT 协议开源，见 [LICENSE](LICENSE)。

> **免责声明：** 本项目仅供学习与研究，不构成任何投资建议。
