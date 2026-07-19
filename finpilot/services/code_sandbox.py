"""通用 Python 代码执行沙箱。

参考阿里 OpenSandbox 的分层隔离设计，提供两档模式：

- **lightweight**：subprocess + 资源限制（本地开发）
- **docker**：Docker 容器隔离（生产环境）

安全措施：

- 模块白名单（禁止 os / subprocess / socket / ctypes / sys / signal / shutil / importlib）
- 超时 30 秒自动 kill
- 内存限制 256MB
- 输出截断 10000 字符
- 禁止文件 I/O
- Docker 模式额外提供网络隔离和文件系统隔离
"""

from __future__ import annotations

import contextlib
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from finpilot.services.sandbox_config_loader import (
    DEFAULT_ALLOWED_MODULES,
    DEFAULT_BLOCKED_MODULES,
    DEFAULT_CPU_LIMIT,
    DEFAULT_MAX_OUTPUT_LENGTH,
    DEFAULT_MEMORY_MB,
    DEFAULT_TIMEOUT_SECONDS,
    get_code_sandbox_config,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 白名单与安全检查（基线常量, 来自 sandbox_config_loader, 保持单一事实来源）
# ---------------------------------------------------------------------------

# 允许的模块（白名单之外的 import 都会在执行前被拒绝）
ALLOWED_MODULES: frozenset[str] = DEFAULT_ALLOWED_MODULES

# 禁止的模块（额外黑名单，覆盖白名单之外的所有）
_BANNED_MODULES: frozenset[str] = DEFAULT_BLOCKED_MODULES

MAX_STDOUT_CHARS = DEFAULT_MAX_OUTPUT_LENGTH
MAX_STDERR_CHARS = 5000
DEFAULT_TIMEOUT = DEFAULT_TIMEOUT_SECONDS
MEMORY_LIMIT_MB = DEFAULT_MEMORY_MB

# 安全 Preamble：在用户代码前注入，拦截危险 import 和内置函数
# 注意: _safe_import 通过闭包持有白名单与原始 __import__, 不依赖全局变量,
# 因此末尾 del 清理可见名后仍可正常工作（修复 del 后 NameError 问题）。
_SAFETY_PREAMBLE = """
import builtins as _builtins

_BANNED_IMPORTS = frozenset({banned_repr})
_ALLOWED_IMPORTS = frozenset({allowed_repr})

_orig_import = _builtins.__import__
# 在禁用前捕获真实 open/exec/eval, 供已授权包导入时临时恢复（闭包持有, del 后仍可用）
_real_open = _builtins.open
_real_exec = _builtins.exec
_real_eval = _builtins.eval

def _make_safe_import(_allow, _real_import, _bi, _r_open, _r_exec, _r_eval):
    _depth = [0]
    def _safe_import(name, *args, **kwargs):
        top = name.split('.')[0]
        if top in _allow:
            if _depth[0] == 0:
                # 进入授权包初始化: 临时恢复 open/exec/eval 供其使用
                _bi.open = _r_open
                _bi.exec = _r_exec
                _bi.eval = _r_eval
            _depth[0] += 1
            try:
                return _real_import(name, *args, **kwargs)
            finally:
                _depth[0] -= 1
                if _depth[0] == 0:
                    # 回到用户代码: 重新禁用
                    _bi.open = None
                    _bi.exec = None
                    _bi.eval = None
        # 传递性导入: 处于已授权包初始化过程中时, 允许其内部依赖（如 numpy 需 _io）
        if _depth[0] > 0:
            return _real_import(name, *args, **kwargs)
        raise ImportError(f"Module '{{name}}' is not allowed in sandbox")
    return _safe_import

_builtins.__import__ = _make_safe_import(
    _ALLOWED_IMPORTS, _orig_import, _builtins, _real_open, _real_exec, _real_eval
)

# 屏蔽 open / exec / eval（用户代码层面禁用; 授权包导入时由 safe_import 临时恢复）
_builtins.open = None
_builtins.exec = None
_builtins.eval = None

# 清理可见名（_safe_import 已通过闭包持有所需引用, 无需全局）
del _make_safe_import, _orig_import, _real_open, _real_exec, _real_eval
del _BANNED_IMPORTS, _ALLOWED_IMPORTS, _builtins
"""


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class SandboxResult:
    """沙箱执行结果."""

    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    execution_time_ms: float = 0.0
    truncated: bool = False


# ---------------------------------------------------------------------------
# CodeSandbox
# ---------------------------------------------------------------------------


class CodeSandboxError(Exception):
    """沙箱执行异常."""


class CodeSandbox:
    """通用 Python 代码沙箱.

    根据配置 ``SANDBOX_MODE`` 自动选择执行模式：

    - ``lightweight``：subprocess 隔离（默认）
    - ``docker``：Docker 容器隔离
    """

    def __init__(
        self,
        tenant_id: str | None = None,
        db: Session | None = None,
    ) -> None:
        """初始化沙箱.

        Args:
            tenant_id: 租户 ID。提供时从 DB 加载租户级沙箱配置;
                为 None 时使用硬编码默认（向后兼容）。
            db: 可选数据库会话, 供配置加载器使用。
        """
        # 从 DB 加载租户沙箱配置; 未提供 tenant_id 时使用硬编码默认
        if tenant_id is not None:
            cfg = get_code_sandbox_config(tenant_id, db)
        else:
            from finpilot.services.sandbox_config_loader import CodeSandboxConfig

            cfg = CodeSandboxConfig()

        self._docker_bin = shutil.which("docker")
        self.allowed_modules: frozenset[str] = cfg.allowed_modules
        self.blocked_modules: frozenset[str] = cfg.blocked_modules
        self.timeout_seconds: int = cfg.timeout_seconds
        self.memory_mb: int = cfg.memory_mb
        self.cpu_limit: int = cfg.cpu_limit
        self.max_output_length: int = cfg.max_output_length
        self.network_disabled: bool = cfg.network_disabled
        # 执行模式: DB 配置 > 环境变量 SANDBOX_MODE > 默认 lightweight
        # （cfg.mode 已在 loader 内部处理过 fallback，这里只兜底环境变量覆盖）
        env_mode = os.environ.get("SANDBOX_MODE", "").strip()
        if env_mode in ("lightweight", "docker"):
            self.mode = env_mode
        else:
            self.mode = cfg.mode
        self.docker_image: str = cfg.docker_image

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def execute(self, code: str, timeout: int | None = None) -> SandboxResult:
        """安全执行 Python 代码。

        Args:
            code: 要执行的 Python 源码。
            timeout: 超时秒数; None 时使用沙箱配置的 timeout_seconds。

        Returns:
            SandboxResult 包含 stdout / stderr / exit_code / execution_time_ms。
        """
        if timeout is None:
            timeout = self.timeout_seconds
        if self.mode == "docker":
            return self._execute_docker(code, timeout)
        return self._execute_lightweight(code, timeout)

    def health_check(self) -> bool:
        """检查沙箱是否可用。

        Returns:
            True 如果沙箱可以正常执行代码。
        """
        try:
            result = self.execute("print('ok')", timeout=10)
            return result.exit_code == 0 and "ok" in result.stdout
        except Exception:
            logger.exception("sandbox_health_check_failed")
            return False

    # -----------------------------------------------------------------------
    # Lightweight mode
    # -----------------------------------------------------------------------

    def _build_preamble(self) -> str:
        """构建安全 preamble 字符串，注入模块白名单/黑名单。"""
        allowed_repr = repr(sorted(self.allowed_modules))
        banned_repr = repr(sorted(self.blocked_modules))
        return _SAFETY_PREAMBLE.format(allowed_repr=allowed_repr, banned_repr=banned_repr)

    def _build_resource_limits(self) -> str:
        """构建子进程资源限制代码（轻量模式, 注入到子进程内执行 setrlimit）。

        通过在子进程内调用 resource.setrlimit 限制 CPU / 内存 / 文件大小 / 进程数,
        设置早于安全 preamble, 因此使用原始 import。setrlimit 在部分平台
        （如 Windows 或受限容器）不可用, 整体包裹在 try/except 中静默降级。
        """
        cpu_seconds = self.timeout_seconds + 5  # 略大于超时, 避免误杀
        mem_bytes = self.memory_mb * 1024 * 1024
        fsize_bytes = 64 * 1024 * 1024  # 64MB 最大文件写入
        nproc = max(self.cpu_limit, 1)
        return (
            "try:\n"
            "    import resource as _resource\n"
            "    try:\n"
            f"        _resource.setrlimit(_resource.RLIMIT_CPU, ({cpu_seconds}, {cpu_seconds}))\n"
            f"        _resource.setrlimit(_resource.RLIMIT_AS, ({mem_bytes}, {mem_bytes}))\n"
            f"        _resource.setrlimit(_resource.RLIMIT_FSIZE, ({fsize_bytes}, {fsize_bytes}))\n"
            f"        _resource.setrlimit(_resource.RLIMIT_NPROC, ({nproc}, {nproc}))\n"
            "    except Exception:\n"
            "        pass\n"
            "    finally:\n"
            "        del _resource\n"
            "except ImportError:\n"
            "    pass\n"
        )

    def _execute_lightweight(self, code: str, timeout: int) -> SandboxResult:
        """轻量模式：subprocess 执行 Python 代码."""
        resource_limits = self._build_resource_limits()
        preamble = self._build_preamble()
        full_code = resource_limits + preamble + "\n" + code

        # 写入临时文件（subprocess 模式需要）
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            prefix="sandbox_",
            delete=False,
            encoding="utf-8",
        ) as f:
            f.write(full_code)
            script_path = f.name

        start = self._now_ms()
        try:
            proc = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tempfile.gettempdir(),
                env={
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONIOENCODING": "utf-8",
                    "HOME": tempfile.gettempdir(),
                    "PATH": os.environ.get("PATH", ""),
                },
            )
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
            exit_code = proc.returncode
        except subprocess.TimeoutExpired:
            stdout = ""
            stderr = f"Execution timed out after {timeout}s"
            exit_code = -1
        except Exception as exc:
            stdout = ""
            stderr = str(exc)
            exit_code = -1
        finally:
            elapsed = self._now_ms() - start
            self._cleanup(script_path)

        stdout, stderr, truncated = self._truncate_output(stdout, stderr)

        return SandboxResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            execution_time_ms=elapsed,
            truncated=truncated,
        )

    # -----------------------------------------------------------------------
    # Docker mode
    # -----------------------------------------------------------------------

    def _execute_docker(self, code: str, timeout: int) -> SandboxResult:
        """Docker 模式：通过 docker run 隔离执行。

        需要 Docker daemon 运行且 ``SANDBOX_MODE=docker``。
        """
        if not self._docker_bin:
            raise CodeSandboxError(
                "Docker 未安装或不在 PATH 中。请安装 Docker 或设置 SANDBOX_MODE=lightweight"
            )

        preamble = self._build_preamble()
        full_code = preamble + "\n" + code

        # 写入临时脚本（mount 进容器）
        tmp_dir = Path(tempfile.gettempdir()) / "sandbox_docker"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        script_path = tmp_dir / "script.py"
        script_path.write_text(full_code, encoding="utf-8")

        start = self._now_ms()
        try:
            proc = subprocess.run(
                [
                    self._docker_bin,
                    "run",
                    "--rm",
                    "--network=none",
                    f"--memory={self.memory_mb}m",
                    f"--cpus={self.cpu_limit}",
                    "--ulimit=nofile=64:128",
                    "--read-only",
                    "--tmpfs=/tmp:size=64m,noexec,nosuid",
                    "--cap-drop=ALL",
                    "--security-opt=no-new-privileges",
                    "-v",
                    f"{script_path}:/sandbox/script.py:ro",
                    "-w",
                    "/sandbox",
                    self.docker_image,
                    "python",
                    "/sandbox/script.py",
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
            exit_code = proc.returncode
        except subprocess.TimeoutExpired:
            stdout = ""
            stderr = f"Execution timed out after {timeout}s"
            exit_code = -1
        except Exception as exc:
            stdout = ""
            stderr = str(exc)
            exit_code = -1
        finally:
            elapsed = self._now_ms() - start
            self._cleanup(str(script_path))

        stdout, stderr, truncated = self._truncate_output(stdout, stderr)

        return SandboxResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            execution_time_ms=elapsed,
            truncated=truncated,
        )

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _now_ms() -> float:
        import time
        return time.perf_counter() * 1000

    def _truncate_output(self, stdout: str, stderr: str) -> tuple[str, str, bool]:
        """按沙箱配置截断 stdout / stderr, 返回 (stdout, stderr, truncated)。"""
        max_out = self.max_output_length
        max_err = max(max_out // 2, 1)
        truncated = False
        if len(stdout) > max_out:
            stdout = stdout[:max_out] + "\n\n[... output truncated ...]"
            truncated = True
        if len(stderr) > max_err:
            stderr = stderr[:max_err] + "\n\n[... stderr truncated ...]"
            truncated = True
        return stdout, stderr, truncated

    @staticmethod
    def _cleanup(path: str) -> None:
        with contextlib.suppress(OSError):
            os.unlink(path)
