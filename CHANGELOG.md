# Changelog

本项目所有重要变更均记录于此。版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### 新增
- **开源项目标配**：CONTRIBUTING.md / CODE_OF_CONDUCT.md / SECURITY.md / .github/ISSUE_TEMPLATE / .github/PULL_REQUEST_TEMPLATE.md / .github/workflows/ci.yml / .github/dependabot.yml / .github/FUNDING.yml
- **CI workflow**：GitHub Actions 矩阵测试 Python 3.10–3.13 + 前端 TypeScript 编译 + Vite 构建
- **README 美化**：新增 banner.svg（带渐变与 LOGO 的横幅）+ workflow.svg（ReAct 工作流图）+ 完整徽章矩阵
- **.gitignore 强化**：补充密钥文件（*.pem/*.key/id_rsa 等）、缓存（.pytest_cache/.mypy_cache）、IDE（.vscode/.idea）、构建产物（build/.eggs）等过滤规则

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
