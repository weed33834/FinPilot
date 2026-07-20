## 变更类型

- [ ] 🐛 Bug 修复（fix）
- [ ] ✨ 新功能（feat）
- [ ] 🎨 UI / 样式（style）
- [ ] ♻️ 重构（refactor）
- [ ] 🚀 性能优化（perf）
- [ ] 📚 文档（docs）
- [ ] ✅ 测试（test）
- [ ] 🔧 构建 / 工具（chore）

## 动机

<!-- 简述为什么要做这个改动。关联 Issue：Closes #xxx -->

## 改动内容

<!-- 主要改动点，必要时附代码片段或截图 -->

## 验证方式

<!-- 你怎么验证改动的？例如：
- 后端启动无报错：`uvicorn finpilot_equity.web_app.main:app --port 8001`
- 前端 TS 编译 0 错误：`cd frontend && npx tsc --noEmit`
- 手动测试：在 Agent 对话框输入 "..."，看到 "..."
-->

## 检查清单

- [ ] 已本地验证改动有效
- [ ] 后端 `python -c "import finpilot.api.router"` 无报错
- [ ] 前端 `npx tsc --noEmit` 0 错误
- [ ] 未提交 `.env` / `*.db` / 密钥等敏感文件
- [ ] 新增功能已在 [CHANGELOG.md](../CHANGELOG.md) Unreleased 段记录
- [ ] 新增 API / 模块 / 环境变量已同步 [docs/](../docs/) 与 [README.md](../README.md)
- [ ] 提交信息遵循 Conventional Commits（见 [CONTRIBUTING.md](../CONTRIBUTING.md)）

## 截图 / 录屏（可选）

<!-- UI 改动建议附前后对比 -->

## 破坏性变更

- [ ] 本 PR 包含破坏性变更
- [ ] 已在 CHANGELOG 中标注 BREAKING CHANGE
- [ ] 已在 PR 描述中说明迁移路径
