# Changelog

本项目所有重要变更均记录于此。版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Added
- **Mobile-first responsive adaptation**: dedicated `*Mobile.tsx` pages plus a `MobileShell` (bottom tab + more-sheet); 15+ desktop-only admin pages now degrade gracefully to an "open on desktop" prompt on small screens.
- **Frontend full i18n (en / zh-CN)** via i18next across core flows, with language switching.
- **Documentation overhaul**: English-primary `README.md` with switchable `README.zh-CN.md` / `README.ja.md`; `docs/ARCHITECTURE.md`, `docs/API.md`, `docs/DEPLOYMENT.md` rewritten in English with Mermaid diagrams.
- **Package metadata**: `frontend/package.json` and `setup.py` now carry description / repository / license / long-description.

### Fixed
- **Dashboard crash hardening**: `DashboardLists` and `DashboardCharts` now guard against undefined `items` / `data`, eliminating white-screen renders when the payload is empty or missing.

## [2.0.0] — 2026-07-27

### 🚀 重大版本：企业财务智能体平台

### 新增

#### 财务智能体增强能力（阶段 C）
- **财务校验引擎**：`/api/v1/validation` — 数据一致性校验、试算平衡、勾稽关系验证
- **多智能体辩论**：Bull/Bear 对抗辩论编排，可配置论轮数（`FINPILOT_DEBATE_MAX_ROUNDS`），支持结构化辩论纪要输出
- **可解释性分析**：`/api/v1/explainability` — 模型决策路径可视化、特征重要性排序
- **风险分析**：`/api/v1/risk` — 多维度风险评估（市场/信用/操作/流动性）

#### 财务建模增强（Phase 1）
- **比率分析**：`/api/v1/ratios` — 盈利能力/偿债能力/营运能力/成长能力四大类比率自动计算
- **三表建模**：`/api/v1/three_statement` — DCF/DDM/LBO 增强，利润表/资产负债表/现金流量表联动建模
- **数据连接管理**：`/api/v1/data_connections` — 外部数据源（数据库/API/文件）统一接入与凭证管理

#### 扩展体系完善
- **回测增强**：`/api/v1/backtesting` — 多策略回测、绩效归因、夏普/最大回撤等指标
- **因子挖掘**：`/api/v1/factor_mining` — 基本面/技术面/另类数据因子库
- **MCP 服务器管理**：`/api/v1/mcp_servers` — MCP 协议服务器注册/启停/状态监控
- **技能管理**：`/api/v1/skills` — 可插拔技能注册与调用
- **工具管理**：`/api/v1/tools` — 工具注册/参数校验/调用日志
- **提示词管理**：`/api/v1/prompts` — 系统提示词版本管理与 A/B 测试
- **沙箱配置**：`/api/v1/sandbox_configs` — 代码执行沙箱安全策略配置

#### 运维与可观测性
- **运行时日志**：`/api/v1/runtime_logs` — 实时日志流、按模块/级别过滤
- **管理仪表盘**：`/api/v1/dashboard` — 系统状态总览、模块健康度
- **用户仪表盘**：`/api/v1/dashboard/user` — 用户维度用量统计
- **报告订阅调度**：`/api/v1/report_subscriptions` — 定时生成 + 邮件/Webhook 推送
- **报告模板管理**：`/api/v1/report_templates` — 模板 CRUD + 变量替换

#### Agent 鲁棒性增强
- **死循环检测**：`FINPILOT_GUARDRAILS_LOOP_LIMIT` — 同一工具连续调用 N 次无进展自动终止
- **上下文压缩**：`FINPILOT_GUARDRAILS_CONTEXT_TOKENS` — Token 超阈值自动压缩历史
- **幻觉校验**：`FINPILOT_GUARDRAILS_HALLUCINATION_CHECK` — 关键事实回查验证

#### 基础设施
- **Route 数量**：从 v1.0.0 的 ~25 条扩展至 **41 条**子路由
- **健康检查**：`GET /api/v1/` 返回 `{"status": "ok", "version": "2.0"}`
- **前端兼容路由**：`compat.py` 确保旧版前端路径不 404

### 变更
- **版本号**：`setup.py` 1.0.0 → 2.0.0；`main.py` version 参数同步更新
- **路由架构**：扩展路由采用 try/except 懒加载，单个模块失败不阻断其他路由
- **辩论引擎**：Bull/Bear Agent 共享上下文，结构化输出辩论纪要（论点/反驳/证据/置信度）

## [1.0.0] — 2026-07-20

### 🎉 首个正式版本

### 新增

#### 智能体与对话
- **LangGraph ReAct 智能体**：agent → tools → finalize 循环，最多 5 轮工具调用
- **SSE 流式聊天**：`/api/v1/agent/chat/stream` 用 `agent.stream(stream_mode="updates")` 实时推送 ReAct 思考步骤
- **ReAct 输出解析器**：兼容标准三段式、`<tool_call>` XML、`<answer>` 标签三种 LLM 输出格式
- **降级路径**：LLM 不可用时按 intent 直接调用工具，不阻断主流程
- **心跳保护**：15s 无事件推送 `…` 防止前端误判超时
- **会话持久化**：MemorySaver（默认）与 SQLite（`FINPILOT_CHECKPOINT_BACKEND=sqlite`）两种检查点后端

#### 对话即控制中枢
- **斜杠命令系统**：19 条命令覆盖数据/研报/分析/系统/管理五大类
- **SlashCommandPalette 组件**：模糊搜索 + 键盘导航 + 按分类分组 + 角色过滤
- **权限分级**：admin 可调用全部命令，user 仅可调用 9 条非敏感命令
- **多词命令名**：支持 `/reports generate`、`/admin status` 等复合命令
- **带空格参数**：最后一个参数吃掉剩余值，支持 `/reports generate 600519 贵州茅台`

#### 错误系统
- **FetchError 类**：携带 status/url/method/bodyText/code，让 fetch 调用复用统一错误系统
- **级别化高亮**：network（灰）/auth（黄）/client（橙）/server（红）/unknown（红）五色警示灯
- **脉冲动画**：光晕 + 渐变背景 + 左侧色条 + 入场动画，深浅主题均清晰可见
- **精确错误信息**：`[POST /agent/chat/stream] 500 服务器内部错误 — KeyError: 'react_steps'`
- **422 参数校验**：字段级错误拼接，如 `body.question: field required`

#### LLM 供应商
- **多供应商配置**：数据库优先 + 环境变量回退 + 60s TTL 缓存
- **MoonWeaver 支持**：OpenAI 兼容协议，base_url=https://api.587.lol/v1
- **ModelRouter**：按问题复杂度路由模型档位（low/medium/high）
- **供应商测试**：管理后台一键测试连通性

#### 前端 UI
- **AgentChatPage 改版**：memo 优化、消息入场动画、柔和气泡、圆形渐变头像
- **MarkdownRenderer**：自实现轻量 Markdown 解析 + DOMPurify XSS 清洗 + 代码块语法高亮
- **ReasoningChain**：可折叠推理链面板
- **置信度徽章**：agent 回复显示置信度百分比
- **细化菜单**：复制/重新生成/添加细节/更简洁/润色/删除
- **文件上传**：base64 编码 + 后端解析注入 agent 上下文

#### 安全合规
- **ABAC 访问控制**：基于属性的权限模型
- **TOTP 双因子认证**：pyotp 实现
- **PII 脱敏**：敏感信息自动脱敏
- **审计日志**：所有敏感操作留痕
- **角色分级**：admin / user 二级权限

#### 文档与基础设施
- **API.md**：完整 API 端点文档
- **ARCHITECTURE.md**：架构设计文档
- **DEPLOYMENT.md**：本地/Docker/生产部署指南
- **.env.example**：环境变量示例
- **README.md**：新增斜杠命令、错误系统、环境变量等章节

### 变更

- **Dockerfile**：改用完整 `requirements.txt` 替代 `requirements-equity.txt`，确保 langgraph/mcp/RAG 等模块可用
- **setup.py**：版本号 `0.1.5` → `1.0.0`；classifiers 移除 Python 3.6-3.9，新增 3.12/3.13；`python_requires` 放宽至 `<3.14`
- **frontend/package.json**：版本号 `0.37.0` → `1.0.0`
- **components.json**：修复 `utils` 别名路径 `src/lib/utils` → `src/utils`
- **.gitignore**：添加 `!.env.example` 例外，确保示例文件可提交
- **SSE 重构**：`run_agent`（同步 invoke）→ `agent.stream`（流式 updates），解决前端卡 1-3 分钟误判网络错误的问题

### 修复

- **SSE 流式只返回 start 事件**：根因是 `run_agent` 一次性同步执行，所有 ReAct 步骤在服务端完成后才开始推送。改为 `agent.stream` 后每个节点完成即时推送
- **LLM 输出 `<tool_call>` 格式解析失败**：增强 `parse_react_output` 兼容 `<tool_call>` / `<function>` / `<answer>` XML 风格
- **TypeScript TS6133 unused 错误**：清理 `errors.ts` 中未使用的 `fallback` 参数与 `SandboxManagement.tsx` 中未使用的 import
- **chat 消息流式重渲染**：抽出 `ChatMessageRow` 用 `memo` 包裹，流式 token 增量只重渲染当前消息

## [0.1.5] — 早期内部版本

- 基础智能问答、文档解析、运行记录、报告与审批、安全合规基线
- LangGraph ReAct 智能体（同步 invoke）
- 多格式文档解析器（PDF/DOCX/Excel/CSV）
- RAG 检索（BM25 + 向量 + RRF 融合）
- ABAC + TOTP + PII 脱敏 + 审计日志
