# TODO: requires finpilot.database.models.McpServerConfig (当前 FinPilot 数据库模型中尚无此表，需后续补充)
# TODO: requires external package `httpx` (HTTP 客户端，用于 SSE / streamable_http 传输)
# TODO: requires external package `mcp` (Model Context Protocol 协议相关，可选；本模块为原生实现，未直接依赖 mcp SDK)
"""MCP 客户端 — 真实的 Model Context Protocol 连接实现.

支持三种传输方式:
- stdio: 启动子进程，通过 stdin/stdout 通信 (JSON-RPC)
- sse: Server-Sent Events + HTTP POST
- streamable_http: HTTP 请求/响应 (JSON-RPC over HTTP)

协议流程:
1. initialize — 握手，交换 capabilities
2. tools/list — 发现服务器可用工具
3. tools/call — 调用工具

连接管理:
- McpConnectionManager 维护连接池，按 server_id 复用连接。
- 由于本应用使用同步 SQLAlchemy + 同步路由，所有异步 MCP 操作在
  一个独立后台线程的事件循环中执行，通过 run_async() 提交协程。
  这样 stdio 子进程 / SSE 长连接可以跨请求存活，实现真正的连接池。
"""

from __future__ import annotations

import asyncio
import atexit
import json
import logging
import os
import shlex
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy.orm import Session

from finpilot.database.models import McpServerConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# MCP 协议版本（握手时声明，服务器返回的版本会被采纳）
_DEFAULT_PROTOCOL_VERSION = "2024-11-05"

# 客户端信息
_CLIENT_INFO = {"name": "finpilot", "version": "1.0.0"}

# 连接超时（秒）—— 建立 transport 连接
CONNECT_TIMEOUT = 10

# 请求超时（秒）—— 单次 JSON-RPC 请求
REQUEST_TIMEOUT = 30

# 连接重试次数
MAX_RETRIES = 3

# 重试基础退避（秒），指数退避: base * 2^attempt
RETRY_BASE_DELAY = 0.5


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class McpError(Exception):
    """MCP 客户端基础异常."""

    pass


class McpConnectionError(McpError):
    """连接异常 — 连接被拒绝、超时、传输错误等."""

    pass


class McpTimeoutError(McpError):
    """请求超时异常."""

    pass


class McpProtocolError(McpError):
    """协议异常 — JSON-RPC error 响应、协议违反等."""

    pass


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class McpTool:
    """MCP 工具描述.

    Attributes:
        name: 工具名称（服务器内唯一）。
        description: 工具描述。
        input_schema: 工具参数的 JSON Schema（对应 MCP 的 inputSchema）。
    """

    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# SSE 解析工具
# ---------------------------------------------------------------------------


def _parse_sse_messages(text: str) -> list[dict[str, Any]]:
    """从 SSE 文本中解析出所有 JSON-RPC 消息.

    处理标准 SSE 格式：以空行分隔事件，``data:`` 行承载负载数据。
    """
    messages: list[dict[str, Any]] = []
    data_lines: list[str] = []

    def _flush() -> None:
        if not data_lines:
            return
        raw = "\n".join(data_lines)
        data_lines.clear()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return
        if isinstance(parsed, list):
            messages.extend(m for m in parsed if isinstance(m, dict))
        elif isinstance(parsed, dict):
            messages.append(parsed)

    for line in text.splitlines():
        line = line.rstrip("\r")
        if line.startswith(":"):  # SSE 注释
            continue
        if line.startswith("event:"):
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
        elif line == "":
            _flush()
        # 忽略 id:/retry: 等其它 SSE 字段
    _flush()
    return messages


# ---------------------------------------------------------------------------
# McpClient — 单服务器连接
# ---------------------------------------------------------------------------


class McpClient:
    """单个 MCP 服务器的客户端连接.

    生命周期：
        client = McpClient(config)
        await client.connect()      # 建立 transport
        await client.initialize()   # JSON-RPC 握手
        tools = await client.list_tools()
        result = await client.call_tool("foo", {"x": 1})
        await client.disconnect()
    """

    def __init__(self, config: McpServerConfig) -> None:
        self.config = config
        self._transport = (config.transport or "stdio").lower()

        # transport 状态
        self._process: asyncio.subprocess.Process | None = None
        self._http: httpx.AsyncClient | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._sse_task: asyncio.Task[None] | None = None

        # 请求/响应关联
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._request_id = 0

        # 协议状态
        self._initialized = False
        self._closing = False
        self._server_capabilities: dict[str, Any] = {}
        self._server_info: dict[str, Any] = {}
        self._protocol_version = _DEFAULT_PROTOCOL_VERSION
        self._session_id: str | None = None
        self._connected_at: datetime | None = None

        # SSE 专用
        self._sse_url: str | None = None
        self._post_endpoint: str | None = None
        self._endpoint_ready: asyncio.Event | None = None
        self._sse_error: str | None = None

        # 超时配置
        self._connect_timeout = CONNECT_TIMEOUT
        self._request_timeout = REQUEST_TIMEOUT

    # ------------------------------------------------------------------
    # 公共属性
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        """当前是否处于已连接（已完成握手且 transport 存活）状态."""
        if not self._initialized:
            return False
        if self._transport == "stdio":
            return self._process is not None and self._process.returncode is None
        return self._http is not None and not self._http.is_closed

    @property
    def server_info(self) -> dict[str, Any]:
        return dict(self._server_info)

    @property
    def server_capabilities(self) -> dict[str, Any]:
        return dict(self._server_capabilities)

    # ------------------------------------------------------------------
    # 连接
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """根据 transport 类型建立连接（不包含协议握手）."""
        self._closing = False
        if self._transport == "stdio":
            await self._connect_stdio()
        elif self._transport == "sse":
            await self._connect_sse()
        elif self._transport == "streamable_http":
            await self._connect_streamable_http()
        else:
            raise McpConnectionError(f"不支持的传输方式: {self._transport}")
        self._connected_at = datetime.now()

    async def initialize(self) -> dict[str, Any]:
        """发送 initialize 请求完成握手，并发出 initialized 通知."""
        result = await self._send_request(
            "initialize",
            {
                "protocolVersion": self._protocol_version,
                "capabilities": {},
                "clientInfo": _CLIENT_INFO,
            },
        )
        if isinstance(result, dict):
            self._server_capabilities = result.get("capabilities", {}) or {}
            self._server_info = result.get("serverInfo", {}) or {}
            negotiated = result.get("protocolVersion")
            if negotiated:
                self._protocol_version = negotiated
        # 握手完成后必须发送 initialized 通知
        await self._send_notification("notifications/initialized", {})
        self._initialized = True
        logger.info(
            "mcp_initialized",
            server=self.config.name,
            transport=self._transport,
            protocol_version=self._protocol_version,
        )
        return result if isinstance(result, dict) else {}

    async def list_tools(self) -> list[McpTool]:
        """发送 tools/list，返回服务器暴露的工具列表."""
        result = await self._send_request("tools/list", {})
        tools_raw: list[dict[str, Any]] = []
        if isinstance(result, dict):
            tools_raw = result.get("tools", []) or []
        tools: list[McpTool] = []
        for t in tools_raw:
            if not isinstance(t, dict):
                continue
            tools.append(
                McpTool(
                    name=t.get("name", ""),
                    description=t.get("description", "") or "",
                    input_schema=(
                        t.get("inputSchema")
                        or t.get("input_schema")
                        or {"type": "object", "properties": {}}
                    ),
                )
            )
        logger.info("mcp_list_tools", server=self.config.name, count=len(tools))
        return tools

    async def call_tool(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """发送 tools/call，调用指定工具并返回结果.

        Returns:
            包含 ``content``、``isError``、``text``（提取的文本内容）的字典。
        """
        if arguments is None:
            arguments = {}
        result = await self._send_request(
            "tools/call", {"name": name, "arguments": arguments}
        )
        if not isinstance(result, dict):
            result = {}
        content = result.get("content", []) or []
        text_parts = [
            c.get("text", "")
            for c in content
            if isinstance(c, dict) and c.get("type") == "text"
        ]
        return {
            "content": content,
            "isError": bool(result.get("isError", False)),
            "text": "\n".join(text_parts),
            "raw": result,
        }

    async def disconnect(self) -> None:
        """关闭连接：终止子进程、关闭 HTTP 客户端、取消后台任务."""
        self._closing = True
        was_initialized = self._initialized
        self._initialized = False

        # 取消后台读取任务
        tasks = [
            t
            for t in (self._reader_task, self._stderr_task, self._sse_task)
            if t is not None and not t.done()
        ]
        for t in tasks:
            t.cancel()
        for t in tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        self._reader_task = None
        self._stderr_task = None
        self._sse_task = None

        # 终止子进程
        if self._process is not None and self._process.returncode is None:
            try:
                self._process.terminate()
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    self._process.kill()
                    await self._process.wait()
            except Exception as exc:  # noqa: BLE001
                logger.debug("mcp_process_terminate_failed", error=str(exc))
        self._process = None

        # 关闭 HTTP 客户端
        if self._http is not None and not self._http.is_closed:
            try:
                await self._http.aclose()
            except Exception as exc:  # noqa: BLE001
                logger.debug("mcp_http_close_failed", error=str(exc))
        self._http = None

        # 取消所有挂起的 Future
        for fut in self._pending.values():
            if not fut.done():
                fut.cancel()
        self._pending.clear()

        if was_initialized:
            logger.info("mcp_disconnected", server=self.config.name)

    # ------------------------------------------------------------------
    # 通用请求/通知分发
    # ------------------------------------------------------------------

    async def _send_request(
        self, method: str, params: dict[str, Any] | None = None
    ) -> Any:
        """发送 JSON-RPC 请求并等待对应 id 的响应."""
        self._request_id += 1
        req_id = self._request_id
        msg: dict[str, Any] = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            msg["params"] = params

        if self._transport == "stdio":
            return await self._stdio_request(msg, req_id)
        if self._transport == "sse":
            return await self._sse_request(msg, req_id)
        if self._transport == "streamable_http":
            return await self._http_request(msg, req_id)
        raise McpConnectionError(f"不支持的传输方式: {self._transport}")

    async def _send_notification(
        self, method: str, params: dict[str, Any] | None = None
    ) -> None:
        """发送 JSON-RPC 通知（无 id，不等待响应）."""
        msg: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        if self._transport == "stdio":
            await self._stdio_notification(msg)
        elif self._transport == "sse":
            await self._sse_notification(msg)
        elif self._transport == "streamable_http":
            await self._http_notification(msg)

    def _dispatch_incoming(self, msg: Any) -> None:
        """处理从 transport 读取到的 JSON-RPC 消息（响应或服务器通知）."""
        if not isinstance(msg, dict):
            return
        req_id = msg.get("id")
        if req_id is not None and req_id in self._pending:
            fut = self._pending.pop(req_id)
            if fut.done():
                return
            if "error" in msg and msg["error"] is not None:
                fut.set_exception(McpProtocolError(msg["error"]))
            else:
                fut.set_result(msg.get("result"))
        else:
            # 服务器主动下发的通知/请求，当前不处理，仅记录
            logger.debug(
                "mcp_server_notification",
                server=self.config.name,
                method=msg.get("method"),
            )

    def _build_headers(self) -> dict[str, str]:
        """构造 HTTP 请求头（含鉴权）."""
        headers: dict[str, str] = {}
        # api_key 由 EncryptedString 自动解密
        api_key = getattr(self.config, "api_key", None)
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    # ------------------------------------------------------------------
    # stdio 传输
    # ------------------------------------------------------------------

    def _build_stdio_cmd(self) -> tuple[str, list[str]]:
        """解析 command + args 为 (程序, 参数列表)."""
        command = (self.config.command or "").strip()
        args_raw = self.config.args
        args: list[str] = []
        if args_raw:
            try:
                parsed = json.loads(args_raw)
                if isinstance(parsed, list):
                    args = [str(a) for a in parsed]
                else:
                    args = shlex.split(str(parsed))
            except (json.JSONDecodeError, TypeError):
                args = shlex.split(args_raw)
        # 若未提供独立 args 且 command 含空格，则整体拆分
        if not args and " " in command:
            parts = shlex.split(command)
            return parts[0], parts[1:]
        return command, args

    async def _connect_stdio(self) -> None:
        command, args = self._build_stdio_cmd()
        if not command:
            raise McpConnectionError("stdio 模式需要 command 参数")
        env = {**os.environ, **(self.config.env_vars or {})}
        try:
            self._process = await asyncio.create_subprocess_exec(
                command,
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
        except FileNotFoundError as exc:
            raise McpConnectionError(f"命令不存在: {command}") from exc
        except PermissionError as exc:
            raise McpConnectionError(f"无权限执行命令: {command}") from exc
        self._pending = {}
        self._request_id = 0
        self._reader_task = asyncio.create_task(self._stdio_read_loop())
        self._stderr_task = asyncio.create_task(self._stdio_stderr_drain())

    async def _stdio_read_loop(self) -> None:
        assert self._process is not None and self._process.stdout is not None
        while self._process.returncode is None and not self._closing:
            try:
                line = await self._process.stdout.readline()
            except Exception:  # noqa: BLE001
                break
            if not line:
                break
            text = line.decode("utf-8", errors="replace").strip()
            if not text:
                continue
            try:
                msg = json.loads(text)
            except json.JSONDecodeError:
                # 非 JSON 行（子进程日志），忽略
                logger.debug("stdio_non_json_line", server=self.config.name, line=text[:200])
                continue
            self._dispatch_incoming(msg)
        # 进程退出后，唤醒所有等待中的请求
        self._fail_pending(f"stdio 子进程已退出 (code={self._process.returncode})")

    async def _stdio_stderr_drain(self) -> None:
        assert self._process is not None and self._process.stderr is not None
        while self._process.returncode is None and not self._closing:
            try:
                line = await self._process.stderr.readline()
            except Exception:  # noqa: BLE001
                break
            if not line:
                break
            logger.debug(
                "mcp_stdio_stderr",
                server=self.config.name,
                line=line.decode("utf-8", errors="replace").strip()[:300],
            )

    async def _stdio_request(self, msg: dict[str, Any], req_id: int) -> Any:
        if self._process is None or self._process.returncode is not None:
            raise McpConnectionError("stdio 子进程未运行")
        assert self._process.stdin is not None
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[Any] = loop.create_future()
        self._pending[req_id] = fut
        payload = (json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8")
        try:
            self._process.stdin.write(payload)
            await self._process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as exc:
            self._pending.pop(req_id, None)
            raise McpConnectionError(f"stdio 写入失败: {exc}") from exc
        try:
            return await asyncio.wait_for(fut, timeout=self._request_timeout)
        except asyncio.TimeoutError as exc:
            self._pending.pop(req_id, None)
            raise McpTimeoutError(f"stdio 请求超时: {msg['method']}") from exc

    async def _stdio_notification(self, msg: dict[str, Any]) -> None:
        if self._process is None or self._process.stdin is None or self._process.returncode is not None:
            return
        payload = (json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8")
        try:
            self._process.stdin.write(payload)
            await self._process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            pass

    # ------------------------------------------------------------------
    # SSE 传输
    # ------------------------------------------------------------------

    async def _connect_sse(self) -> None:
        if not self.config.url:
            raise McpConnectionError("sse 模式需要 url 参数")
        base = self.config.url.rstrip("/")
        self._sse_url = base + "/sse"
        self._post_endpoint = base + "/messages"  # 默认，可被 endpoint 事件覆盖
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(self._request_timeout),
            headers=self._build_headers(),
        )
        self._pending = {}
        self._request_id = 0
        self._endpoint_ready = asyncio.Event()
        self._sse_error = None
        self._sse_task = asyncio.create_task(self._sse_read_loop())
        # 等待服务器下发 endpoint 事件（若 SSE 连接失败则立即报错；超时则使用默认 endpoint）
        try:
            await asyncio.wait_for(
                self._endpoint_ready.wait(), timeout=self._connect_timeout
            )
        except asyncio.TimeoutError:
            logger.warning("sse_no_endpoint_event", server=self.config.name)
        if self._sse_error:
            error = self._sse_error
            try:
                await self._http.aclose()
            except Exception:  # noqa: BLE001
                pass
            self._http = None
            raise McpConnectionError(error)

    async def _sse_read_loop(self) -> None:
        assert self._http is not None and self._sse_url is not None

        def _fail(reason: str) -> None:
            self._sse_error = reason
            if self._endpoint_ready is not None and not self._endpoint_ready.is_set():
                self._endpoint_ready.set()
            self._fail_pending(reason)

        try:
            async with self._http.stream("GET", self._sse_url) as resp:
                if resp.status_code != 200:
                    logger.warning(
                        "sse_connect_status",
                        server=self.config.name,
                        status=resp.status_code,
                    )
                    _fail(f"sse 连接失败: HTTP {resp.status_code}")
                    return
                event_type: str | None = None
                data_lines: list[str] = []
                async for line in resp.aiter_lines():
                    if self._closing:
                        break
                    line = line.rstrip("\r\n")
                    if line.startswith("event:"):
                        event_type = line[6:].strip()
                    elif line.startswith("data:"):
                        data_lines.append(line[5:].lstrip())
                    elif line == "":
                        if data_lines:
                            raw = "\n".join(data_lines)
                            self._handle_sse_event(event_type, raw)
                        event_type = None
                        data_lines = []
        except httpx.HTTPError as exc:
            if not self._closing:
                logger.warning("sse_read_error", server=self.config.name, error=str(exc))
                _fail(f"sse 读取错误: {exc}")
        except Exception as exc:  # noqa: BLE001
            if not self._closing:
                logger.warning("sse_read_loop_error", server=self.config.name, error=str(exc))
                _fail(f"sse 读取异常: {exc}")

    def _handle_sse_event(self, event_type: str | None, raw: str) -> None:
        if event_type == "endpoint":
            self._post_endpoint = self._resolve_url(raw.strip())
            if self._endpoint_ready is not None:
                self._endpoint_ready.set()
            return
        # message 事件（或未声明 event 的 data）—— 解析 JSON-RPC
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return
        if isinstance(msg, list):
            for m in msg:
                if isinstance(m, dict):
                    self._dispatch_incoming(m)
        elif isinstance(msg, dict):
            self._dispatch_incoming(msg)

    def _resolve_url(self, path: str) -> str:
        """将可能是相对路径的 endpoint 解析为绝对 URL."""
        if path.startswith("http://") or path.startswith("https://"):
            return path
        base = (self.config.url or "").rstrip("/")
        if not base:
            return path
        if path.startswith("/"):
            return base + path
        return base + "/" + path

    async def _sse_request(self, msg: dict[str, Any], req_id: int) -> Any:
        assert self._http is not None and self._post_endpoint is not None
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[Any] = loop.create_future()
        self._pending[req_id] = fut
        try:
            resp = await self._http.post(
                self._post_endpoint, json=msg, timeout=self._request_timeout
            )
        except httpx.HTTPError as exc:
            self._pending.pop(req_id, None)
            raise McpConnectionError(f"sse POST 错误: {exc}") from exc
        if resp.status_code >= 400:
            self._pending.pop(req_id, None)
            raise McpConnectionError(f"sse POST 失败: HTTP {resp.status_code}")
        # 兼容：部分实现直接在 POST 响应体返回 JSON-RPC 结果
        if resp.content:
            try:
                direct = resp.json()
            except (json.JSONDecodeError, ValueError):
                direct = None
            if isinstance(direct, dict) and direct.get("id") == req_id:
                self._pending.pop(req_id, None)
                if "error" in direct and direct["error"] is not None:
                    raise McpProtocolError(direct["error"])
                return direct.get("result")
        # 标准情况：响应通过 SSE 流异步返回
        try:
            return await asyncio.wait_for(fut, timeout=self._request_timeout)
        except asyncio.TimeoutError as exc:
            self._pending.pop(req_id, None)
            raise McpTimeoutError(f"sse 请求超时: {msg['method']}") from exc

    async def _sse_notification(self, msg: dict[str, Any]) -> None:
        if self._http is None or self._post_endpoint is None:
            return
        try:
            await self._http.post(
                self._post_endpoint, json=msg, timeout=self._request_timeout
            )
        except httpx.HTTPError:
            pass

    # ------------------------------------------------------------------
    # streamable_http 传输
    # ------------------------------------------------------------------

    async def _connect_streamable_http(self) -> None:
        if not self.config.url:
            raise McpConnectionError("streamable_http 模式需要 url 参数")
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(self._request_timeout),
            headers=self._build_headers(),
        )
        self._pending = {}
        self._request_id = 0
        self._session_id = None

    async def _http_request(self, msg: dict[str, Any], req_id: int) -> Any:
        assert self._http is not None
        headers: dict[str, str] = {
            "Accept": "application/json, text/event-stream",
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        try:
            resp = await self._http.post(
                self.config.url, json=msg, headers=headers, timeout=self._request_timeout
            )
        except httpx.HTTPError as exc:
            raise McpConnectionError(f"http 请求错误: {exc}") from exc

        if "mcp-session-id" in resp.headers:
            self._session_id = resp.headers["mcp-session-id"]

        if resp.status_code >= 400:
            raise McpConnectionError(
                f"http 请求失败: HTTP {resp.status_code}: {resp.text[:200]}"
            )

        content_type = resp.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            return self._extract_from_sse(resp.text, req_id)

        # 普通 JSON 响应
        try:
            data = resp.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise McpProtocolError(f"http 响应解析失败: {exc}") from exc

        candidates: list[dict[str, Any]] = []
        if isinstance(data, dict):
            candidates.append(data)
        elif isinstance(data, list):
            candidates.extend(m for m in data if isinstance(m, dict))
        for m in candidates:
            if m.get("id") == req_id:
                if "error" in m and m["error"] is not None:
                    raise McpProtocolError(m["error"])
                return m.get("result")
        raise McpProtocolError(f"http 响应缺少 id={req_id} 的结果")

    def _extract_from_sse(self, text: str, req_id: int) -> Any:
        for m in _parse_sse_messages(text):
            if m.get("id") == req_id:
                if "error" in m and m["error"] is not None:
                    raise McpProtocolError(m["error"])
                return m.get("result")
        raise McpProtocolError(f"http SSE 响应缺少 id={req_id} 的结果")

    async def _http_notification(self, msg: dict[str, Any]) -> None:
        if self._http is None:
            return
        headers: dict[str, str] = {"Accept": "application/json, text/event-stream"}
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        try:
            resp = await self._http.post(
                self.config.url, json=msg, headers=headers, timeout=self._request_timeout
            )
            if "mcp-session-id" in resp.headers:
                self._session_id = resp.headers["mcp-session-id"]
        except httpx.HTTPError:
            pass

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    def _fail_pending(self, reason: str) -> None:
        """将所有挂起的请求标记为失败（transport 关闭时调用）."""
        for req_id, fut in list(self._pending.items()):
            if not fut.done():
                fut.set_exception(McpConnectionError(reason))
        self._pending.clear()


# ---------------------------------------------------------------------------
# 后台事件循环 — 供同步代码提交协程
# ---------------------------------------------------------------------------

_bg_loop: asyncio.AbstractEventLoop | None = None
_bg_thread: threading.Thread | None = None
_bg_lock = threading.Lock()


def _get_bg_loop() -> asyncio.AbstractEventLoop:
    """获取（必要时创建）后台事件循环，运行在独立守护线程中."""
    global _bg_loop, _bg_thread
    with _bg_lock:
        if _bg_loop is None or not _bg_loop.is_running():
            _bg_loop = asyncio.new_event_loop()

            def _run() -> None:
                asyncio.set_event_loop(_bg_loop)
                _bg_loop.run_forever()

            _bg_thread = threading.Thread(
                target=_run, daemon=True, name="mcp-bg-loop"
            )
            _bg_thread.start()
    assert _bg_loop is not None
    return _bg_loop


def run_async(coro: Any, timeout: float = 60.0) -> Any:
    """在后台事件循环中运行协程并阻塞等待结果.

    供同步路由 / Agent 同步代码调用异步 MCP 方法。
    所有协程共享同一个后台循环，因此 stdio 子进程与 SSE 长连接可跨请求复用。
    """
    loop = _get_bg_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=timeout)


# ---------------------------------------------------------------------------
# McpConnectionManager — 连接池 + 路由
# ---------------------------------------------------------------------------


class McpConnectionManager:
    """MCP 连接管理器（单例）.

    维护 server_id -> McpClient 的连接池，提供连接复用、工具发现、
    工具调用、健康检查与统一关闭。
    """

    def __init__(
        self,
        max_retries: int = MAX_RETRIES,
        retry_base_delay: float = RETRY_BASE_DELAY,
        failed_cooldown: float = 30.0,
    ) -> None:
        self._connections: dict[str, McpClient] = {}
        self._lock = asyncio.Lock()
        self._max_retries = max_retries
        self._retry_base_delay = retry_base_delay
        # 失败服务器的冷却期（monotonic 时间戳），避免对不可达服务器反复重试拖慢 Agent
        self._failed_until: dict[str, float] = {}
        self._failed_cooldown = failed_cooldown

    def _is_in_cooldown(self, server_id: str) -> bool:
        until = self._failed_until.get(server_id)
        return until is not None and time.monotonic() < until

    # ------------------------------------------------------------------
    # 连接
    # ------------------------------------------------------------------

    async def get_or_connect(
        self, server_id: str, db: Session, *, force: bool = False
    ) -> McpClient:
        """获取或建立指定服务器的连接（连接池复用）."""
        # 快速路径：已连接则直接返回
        existing = self._connections.get(server_id)
        if existing and existing.is_connected:
            return existing
        # 冷却期内直接失败（force 可绕过，用于显式测试/连接）
        if not force and self._is_in_cooldown(server_id):
            raise McpConnectionError(f"MCP 服务器 {server_id} 连接冷却中（最近失败）")
        config = (
            db.query(McpServerConfig)
            .filter(McpServerConfig.id == server_id)
            .first()
        )
        if not config:
            raise McpConnectionError(f"MCP 服务器不存在: {server_id}")
        return await self._connect_config(config, db, force=force)

    async def _connect_config(
        self, config: McpServerConfig, db: Session, *, force: bool = False
    ) -> McpClient:
        """使用给定配置建立连接，含指数退避重试."""
        server_id = str(config.id)
        # 加锁后再次检查，避免重复连接
        async with self._lock:
            existing = self._connections.get(server_id)
            if existing and existing.is_connected:
                return existing
        if not force and self._is_in_cooldown(server_id):
            raise McpConnectionError(f"MCP 服务器 {config.name} 连接冷却中（最近失败）")

        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            client = McpClient(config)
            try:
                await asyncio.wait_for(
                    client.connect(), timeout=client._connect_timeout
                )
                await asyncio.wait_for(
                    client.initialize(), timeout=client._request_timeout
                )
                # 存入连接池（加锁，处理并发竞争）
                async with self._lock:
                    already = self._connections.get(server_id)
                    if already and already.is_connected:
                        await client.disconnect()
                        return already
                    self._connections[server_id] = client
                # 连接成功，清除冷却标记
                self._failed_until.pop(server_id, None)
                self._update_status(db, config, "connected")
                logger.info(
                    "mcp_connected",
                    server=config.name,
                    server_id=server_id,
                    attempt=attempt + 1,
                )
                return client
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                logger.warning(
                    "mcp_connect_attempt_failed",
                    server=config.name,
                    attempt=attempt + 1,
                    error=str(exc),
                )
                try:
                    await client.disconnect()
                except Exception:  # noqa: BLE001
                    pass
                if attempt < self._max_retries - 1:
                    delay = self._retry_base_delay * (2**attempt)
                    await asyncio.sleep(delay)

        # 最终失败：记录冷却期
        self._failed_until[server_id] = time.monotonic() + self._failed_cooldown
        self._update_status(db, config, "error")
        raise McpConnectionError(
            f"连接 MCP 服务器 {config.name} 失败（重试 {self._max_retries} 次）: {last_exc}"
        )

    async def disconnect_server(self, server_id: str) -> bool:
        """断开并移除指定服务器的连接."""
        async with self._lock:
            client = self._connections.pop(server_id, None)
        if client is None:
            return False
        await client.disconnect()
        return True

    async def disconnect_all(self) -> None:
        """关闭所有连接（应用关闭时调用）."""
        async with self._lock:
            clients = list(self._connections.values())
            self._connections.clear()
        for client in clients:
            try:
                await client.disconnect()
            except Exception as exc:  # noqa: BLE001
                logger.warning("mcp_disconnect_all_failed", error=str(exc))

    # ------------------------------------------------------------------
    # 工具发现与调用
    # ------------------------------------------------------------------

    async def list_server_tools(
        self, server_id: str, db: Session, *, force: bool = False
    ) -> list[McpTool]:
        """列出指定服务器的工具."""
        client = await self.get_or_connect(server_id, db, force=force)
        return await client.list_tools()

    async def discover_all_tools(
        self, tenant_id: str, db: Session
    ) -> list[tuple[str, str, list[McpTool]]]:
        """连接租户下所有启用的 MCP 服务器，收集全部工具.

        Returns:
            元组列表: [(server_id, server_name, [McpTool]), ...]
            连接失败的服务器返回空工具列表，不抛异常（优雅降级）。
        """
        try:
            configs = (
                db.query(McpServerConfig)
                .filter(
                    McpServerConfig.tenant_id == tenant_id,
                    McpServerConfig.is_active.is_(True),
                )
                .order_by(McpServerConfig.priority, McpServerConfig.created_at)
                .all()
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("discover_all_tools_query_failed", error=str(exc))
            return []

        results: list[tuple[str, str, list[McpTool]]] = []
        for cfg in configs:
            server_id = str(cfg.id)
            try:
                client = await self._connect_config(cfg, db)
                tools = await client.list_tools()
                results.append((server_id, cfg.name, tools))
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "discover_tools_failed",
                    server=cfg.name,
                    error=str(exc),
                )
                results.append((server_id, cfg.name, []))
        return results

    async def call_tool(
        self,
        server_id: str,
        tool_name: str,
        arguments: dict[str, Any] | None,
        db: Session,
    ) -> dict[str, Any]:
        """路由工具调用到对应服务器."""
        client = await self.get_or_connect(server_id, db)
        return await client.call_tool(tool_name, arguments or {})

    # ------------------------------------------------------------------
    # 健康检查与状态
    # ------------------------------------------------------------------

    async def health_check(
        self, server_id: str, db: Session
    ) -> dict[str, Any]:
        """测试服务器是否可达.

        Returns:
            {"reachable": bool, "error": str | None, "server_name": str, "transport": str}
        """
        config = (
            db.query(McpServerConfig)
            .filter(McpServerConfig.id == server_id)
            .first()
        )
        if not config:
            return {
                "reachable": False,
                "error": "服务器不存在",
                "server_name": "",
                "transport": "",
            }
        try:
            # 健康检查绕过冷却期，真正尝试连接
            client = await self._connect_config(config, db, force=True)
            return {
                "reachable": True,
                "error": None,
                "server_name": config.name,
                "transport": config.transport,
                "server_info": client.server_info,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "reachable": False,
                "error": str(exc),
                "server_name": config.name,
                "transport": config.transport,
            }

    def get_status(self) -> dict[str, dict[str, Any]]:
        """返回连接池中所有服务器的连接状态（同步方法，供路由直接调用）."""
        # 快照，避免迭代时被后台循环修改
        snapshot = dict(self._connections)
        return {
            sid: {
                "connected": c.is_connected,
                "transport": c.config.transport,
                "server_name": c.config.name,
                "connected_at": c._connected_at.isoformat() if c._connected_at else None,
            }
            for sid, c in snapshot.items()
        }

    def is_connected(self, server_id: str) -> bool:
        """查询某服务器是否已连接（同步）."""
        client = self._connections.get(server_id)
        return bool(client and client.is_connected)

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _update_status(
        self, db: Session, config: McpServerConfig, status: str
    ) -> None:
        """更新数据库中的连接状态（best-effort）."""
        try:
            config.last_status = status
            if status == "connected":
                config.last_connected_at = datetime.now().isoformat()
            db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("update_mcp_status_failed", error=str(exc))
            try:
                db.rollback()
            except Exception:  # noqa: BLE001
                pass


# 模块级单例
mcp_manager = McpConnectionManager()


def _atexit_shutdown() -> None:
    """进程退出时尽力关闭所有连接."""
    try:
        run_async(mcp_manager.disconnect_all(), timeout=5.0)
    except Exception:  # noqa: BLE001
        pass


atexit.register(_atexit_shutdown)
