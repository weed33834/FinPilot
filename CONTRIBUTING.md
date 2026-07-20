# 贡献指引

感谢你对 FinPilot AI 的关注！本文档说明参与贡献的流程与规范。

## 行为准则

参与本项目即代表你同意遵守 [Code of Conduct](CODE_OF_CONDUCT.md)。请在所有交流中保持尊重与友善。

## 如何贡献

我们欢迎以下形式的贡献：

- 报告 Bug 或提出功能建议（[提 Issue](https://github.com/weed33834/FinPilot/issues/new/choose)）
- 提交代码修复或新功能（Pull Request）
- 完善文档（README / docs / 注释）
- 翻译 i18n 文案
- 分享使用经验

## 开发环境准备

```bash
# 1. Fork & clone
git clone https://github.com/<your-username>/FinPilot.git
cd FinPilot

# 2. 创建虚拟环境
python3 -m venv venv
source venv/bin/activate
pip install -e .

# 3. 安装前端依赖
cd frontend && npm install && cd ..

# 4. 启动开发服务
uvicorn finpilot_equity.web_app.main:app --host 0.0.0.0 --port 8001 --reload
# 另开一个终端
cd frontend && npm run dev
```

## 提交 Pull Request

1. **从 `master` 切出新分支**：`git checkout -b feat/your-feature` 或 `fix/your-bugfix`
2. **写好提交信息**：参考下方「提交信息规范」
3. **本地验证**：
   - 后端：`python -c "import finpilot.api.router"` 应无报错
   - 前端：`cd frontend && npx tsc --noEmit` 应 0 错误
4. **不要提交敏感文件**：`.env`、`*.db`、密钥等已在 `.gitignore` 中排除，请勿强制添加
5. **Push 到你的 fork 并发起 PR**：目标分支 `master`，标题简洁明了，描述清楚动机 / 改动 / 验证方式
6. **响应 Review**：根据 maintainer 的反馈调整代码

## 提交信息规范

采用 Conventional Commits 风格：

```
<type>(<scope>): <subject>

<body>

<footer>
```

- **type**：`feat`（新功能）、`fix`（Bug 修复）、`docs`（文档）、`style`（格式）、`refactor`（重构）、`test`（测试）、`chore`（构建/工具）、`perf`（性能）
- **scope**（可选）：影响模块，如 `agent`、`api`、`frontend`、`rag`、`security`
- **subject**：简洁描述，不超过 50 字
- **body**（可选）：详细说明动机、改动内容、注意事项
- **footer**（可选）：BREAKING CHANGE 或关闭 Issue，如 `Closes #123`

示例：

```
feat(agent): 兼容 <tool_call> XML 格式的 ReAct 输出

LLM 输出 <tool_call><function=NAME>...</function></tool_call> 时，
原解析器无法识别走 retry。新增三种 XML 格式兼容。

Closes #42
```

## 代码风格

### Python

- 遵循 [PEP 8](https://peps.python.org/pep-0008/)，行宽建议 ≤ 100
- 类型注解：函数参数与返回值都加注解
- 文档字符串：模块 / 类 / 公共函数用三引号 docstring
- import 顺序：标准库 → 第三方 → 本项目，组间空一行
- 命名：模块/变量 `snake_case`，类 `PascalCase`，常量 `UPPER_SNAKE`

### TypeScript / React

- 启用 `strict` 模式（已在 `tsconfig.json` 配置）
- 启用 `noUnusedLocals` 与 `noUnusedParameters`：不允许未使用的变量与参数
- 函数组件优先，hooks 抽到 `useXxx`
- 命名：组件 `PascalCase`，hooks/工具 `camelCase`，常量 `UPPER_SNAKE`
- 性能敏感组件用 `memo` 包裹，避免不必要的重渲染

### CSS

- 优先使用 Tailwind utility class
- 全局样式放在 `src/index.css`，按模块分段注释
- 避免内联 `style` 属性，除非动态值

## 文档规范

- 新增功能必须同步更新 [CHANGELOG.md](CHANGELOG.md) 的 Unreleased 段
- 新增模块必须在 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) 中描述
- 新增 API 端点必须在 [docs/API.md](docs/API.md) 中记录
- 新增环境变量必须同步 [`.env.example`](.env.example) 与 [README.md](README.md) 的环境变量表

## Issue 规范

提 Issue 请选择对应模板并填写完整信息：

- **Bug 报告**：复现步骤、期望行为、实际行为、环境信息（OS / Python / Node / 浏览器）、日志截图
- **功能建议**：使用场景、期望效果、替代方案、是否愿意提交 PR

## 安全漏洞

**请勿在公开 Issue 中披露安全漏洞。** 请按 [SECURITY.md](SECURITY.md) 中的方式私下报告。

## License

提交的代码将按 [MIT License](LICENSE) 发布。
