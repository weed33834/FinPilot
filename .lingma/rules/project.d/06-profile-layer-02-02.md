1. **Query**: Formulate search terms based on the user's question.
2. **Search**: Query multiple sources (Bing, GitHub, Stack Overflow, official documentation).
3. **Cross-validate**: Key claims require 2+ independent sources.
4. **Synthesize**: Extract and integrate findings; flag conflicts.

> When uncertain, searching beats guessing. Do not fabricate APIs, libraries, or version numbers.

## Tech Stack & Commands (技术栈与命令)
- Primary: Python 3.12+ (async/await + type hints by default)
- Frameworks: FastAPI, Pydantic (按实际改)
- 安装依赖：`pip install -r requirements.txt`
- 运行测试：`pytest`
- 代码检查：`ruff check .`
- 类型检查：`mypy .`
- 写代码前先 `pip list` 查已装包，避免重复安装。
- 优先 httpx 而非 requests，优先 pendulum 而非 datetime。

## References
- 智能体提示词: `@profiles/coding/docs/prompts/system-prompt.md` (按需 Read)
- 架构师角色: `@profiles/coding/docs/prompts/architect-subagent.md` (按需 Read)
- 工程师角色: `@profiles/coding/docs/prompts/engineer-subagent.md` (按需 Read)
- 审查官角色: `@profiles/coding/docs/prompts/critic-subagent.md` (按需 Read)
- 验证员角色: `@profiles/coding/docs/prompts/verifier-subagent.md` (按需 Read)
- 交付角色: `@profiles/coding/docs/prompts/final-subagent.md` (按需 Read)
- 技能注册表: `@profiles/coding/docs/skills/registry.md` (按需 Read)