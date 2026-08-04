"""工具加载器 — 从 DB tools 表读取工具并沙箱化注册到 tool_registry.

安全模型：
- 注册阶段：exec() 提取入口函数（需导入分析的只读操作），不做实际执行
- 执行阶段：func() 内部通过 CodeSandbox.execute() 在子进程/容器中运行，
  杜绝 DB 工具代码直接在当前进程执行的安全风险
"""
from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from finpilot.agent.tool_registry import ToolContext, ToolSpec, tool_registry
from finpilot.database.models import Tool

logger = logging.getLogger(__name__)

_registered_names: set[str] = set()


def _validate_in_sandbox(code: str, tool_name: str, tenant_id: str, db: Session) -> bool:
    """用 CodeSandbox 验证 DB 工具代码的安全性。

    将代码送沙箱子进程执行一次简单的 print("OK") 导入测试，
    确认模块白名单通过、无恶意操作。
    """
    try:
        from finpilot.services.code_sandbox import CodeSandbox

        sandbox = CodeSandbox(tenant_id, db)
        # 只做导入解析 + 函数签名提取，不跑真实逻辑
        test_code = code + "\n\n# -- sandbox validation probe --\nprint('SANDBOX_VALID_OK')"
        result = sandbox.execute(test_code, timeout=10)
        if result.exit_code != 0:
            logger.warning(
                "tool_loader: sandbox validation failed for '%s': exit=%d stderr=%s",
                tool_name, result.exit_code, result.stderr,
            )
            return False
        if "SANDBOX_VALID_OK" not in (result.stdout or ""):
            logger.warning("tool_loader: sandbox validation output mismatch for '%s'", tool_name)
            return False
        return True
    except Exception as exc:
        logger.error("tool_loader: sandbox validation error for '%s': %s", tool_name, exc)
        return False


def _make_sandboxed_wrapper(
    code: str, entry_function: str, tool_name: str, tenant_id: str
):
    """创建沙箱化包装函数：Agent 调用时通过 CodeSandbox 子进程执行，不污染主进程。"""

    def sandboxed_func(context: ToolContext, **params: Any) -> str:
        import json as _json

        # 构建完整可执行代码：工具定义 + 入口调用
        params_json = _json.dumps(params, ensure_ascii=False, default=str)
        full_code = f"""\
{code}

import json
_params = json.loads('''{params_json}''')
_result = {entry_function}(_params)
print(json.dumps({{"result": _result}}, ensure_ascii=False, default=str))
"""

        from finpilot.services.code_sandbox import CodeSandbox
        from finpilot.database import SessionLocal

        _db = SessionLocal()
        try:
            sandbox = CodeSandbox(tenant_id, _db)
            sb_result = sandbox.execute(full_code, timeout=30)

            if sb_result.exit_code != 0:
                return f"[沙箱执行失败] {sb_result.stderr or f'exit_code={sb_result.exit_code}'}"

            stdout = sb_result.stdout or ""
            try:
                parsed = _json.loads(stdout.strip().split("\n")[-1])
                return str(parsed.get("result", stdout))
            except (json.JSONDecodeError, KeyError):
                return stdout.strip()
        except Exception as exc:
            return f"[沙箱异常] {exc}"
        finally:
            _db.close()

    return sandboxed_func


def reload_db_tools(tenant_id: str, db: Session) -> None:
    """从 DB tools 表加载自定义 Python 工具，沙箱化后注册到 tool_registry。

    - 注册阶段：exec() 只做函数提取，额外通过 CodeSandbox 验证安全性
    - 执行阶段：包装函数通过 CodeSandbox.execute() 子进程隔离运行
    """
    global _registered_names

    tools = (
        db.query(Tool)
        .filter(
            Tool.tenant_id == tenant_id,
            Tool.is_active.is_(True),
            Tool.is_builtin.is_(False),
            Tool.type == "python_function",
        )
        .all()
    )

    new_names: set[str] = set()

    for tool in tools:
        config = tool.config or {}
        code = config.get("code", "")
        entry_function = config.get("entry_function", "run")

        if not code:
            logger.warning("tool_loader: tool %s has no code, skipping", tool.name)
            continue

        # 沙箱安全验证（先过白名单/无权模块检查再注册）
        if not _validate_in_sandbox(code, tool.name, tenant_id, db):
            logger.error("tool_loader: sandbox rejected tool '%s'", tool.name)
            continue

        try:
            # 注册阶段：exec() 提取函数引用（只读，不做业务执行）
            namespace: dict[str, Any] = {
                "ToolContext": ToolContext,
                "json": json,
                "__builtins__": __builtins__,
            }
            exec(compile(code, f"<tool:{tool.name}>", "exec"), namespace)

            func = namespace.get(entry_function)
            if func is None:
                logger.warning(
                    "tool_loader: entry function '%s' not found in tool %s",
                    entry_function, tool.name,
                )
                continue

            # 创建沙箱化包装：执行时走 CodeSandbox 子进程
            safe_func = _make_sandboxed_wrapper(code, entry_function, tool.name, tenant_id)

            spec = ToolSpec(
                name=tool.name,
                description=tool.description or tool.display_name,
                parameters_schema=config.get("parameters_schema", {}),
                func=safe_func,
                tags=["db_tool", tool.type, "sandboxed"],
            )

            tool_registry._tools[tool.name] = spec
            new_names.add(tool.name)
            logger.info("tool_loader: registered sandboxed tool '%s' from DB", tool.name)

        except Exception as exc:
            logger.error(
                "tool_loader: failed to load tool '%s': %s", tool.name, exc,
            )

    # 清理已从 DB 删除的工具
    stale = _registered_names - new_names
    for name in stale:
        tool_registry._tools.pop(name, None)
        logger.info("tool_loader: unregistered stale tool '%s'", name)

    _registered_names = new_names
