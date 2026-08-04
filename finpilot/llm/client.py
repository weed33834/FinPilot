"""
LLM client - a unified wrapper over the openai SDK for multi-vendor calls.

- openai / anthropic / ollama all speak the OpenAI-compatible protocol
- Provides synchronous chat, streaming output, and multimodal image analysis
- Uniformly records latency and token usage for every call

Demo fallback: when the env var ``FINPILOT_LLM_DEMO_FALLBACK`` is set to a
truthy value (e.g. ``1``), any ``LLMUnavailableError`` raised during a chat
call will be swallowed and replaced with a deterministic canned response, so
the rest of the data pipeline (NL2SQL → agent → report) can be exercised
end-to-end even when the configured LLM provider is unreachable (e.g. invalid
API key, network outage). The fallback is OFF by default and MUST NOT be
enabled in production.
"""
import logging
import os
import time
from typing import Iterator

import openai
from openai import OpenAI
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .config import LLMConfig

logger = logging.getLogger(__name__)

# ── LLM 调用韧性配置（环境变量可调）──────────────────────────────────
# 单次请求超时（秒）：SDK 默认 600s 过长，单次卡死会拖死整条 ReAct 链。
_LLM_CALL_TIMEOUT = float(os.getenv("FINPILOT_LLM_CALL_TIMEOUT", "60"))
# 最大重试次数（含首次）：仅对瞬态错误（超时/连接/限流/5xx）重试，
# 认证/参数错误等不重试。指数退避 1s→2s→4s… 上限 10s。
_LLM_MAX_RETRIES = int(os.getenv("FINPILOT_LLM_MAX_RETRIES", "3"))

# 瞬态错误：值得重试的 OpenAI SDK 异常（均属 openai.OpenAIError 子类）
_RETRYABLE_ERRORS = (
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.RateLimitError,
    openai.InternalServerError,
)


def _llm_retry(func):
    """tenacity 重试装饰器：仅对瞬态 LLM 错误指数退避重试，其余立即抛出。

    - stop: 最多 _LLM_MAX_RETRIES 次（含首次）
    - wait: 指数退避 min=1s max=10s multiplier=1
    - retry: 仅 _RETRYABLE_ERRORS 触发重试
    - reraise: 重试耗尽后抛原始异常（而非 RetryError），便于上层按
      openai.OpenAIError 统一捕获并走 demo fallback / LLMUnavailableError
    """
    return retry(
        stop=stop_after_attempt(_LLM_MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(_RETRYABLE_ERRORS),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )(func)


def _demo_fallback_enabled() -> bool:
    """``FINPILOT_LLM_DEMO_FALLBACK=1`` enables the canned-response fallback."""
    return os.getenv("FINPILOT_LLM_DEMO_FALLBACK", "").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _canned_response(system_prompt: str, user_prompt: str) -> str:
    """Deterministic canned response used when the real LLM is unreachable.

    Includes enough structure that downstream NL2SQL / agent / report flows
    can be exercised without a real model. Clearly marked as a demo answer.
    """
    snippet = (user_prompt or "")[:120].replace("\n", " ")
    return (
        "[DEMO FALLBACK] 真实 LLM 调用失败，已启用演示模式返回。\n"
        f"系统提示: {(system_prompt or '')[:60]}\n"
        f"用户输入: {snippet}\n"
        "（如需启用真实 LLM，请配置有效的 API Key 并关闭 FINPILOT_LLM_DEMO_FALLBACK）"
    )

# Security facade (migrated from legacy): injection detection + audit. If the
# import fails we degrade to a no-op so LLMClient still works in environments
# where the security package is absent (keeps existing deployments intact).
try:
    from finpilot.security.guard import guard_llm_call, InjectionBlockedError
except Exception:  # noqa: BLE001
    class InjectionBlockedError(Exception):  # type: ignore[no-redef]
        """Fallback exception type used when the security package is unavailable."""

    def guard_llm_call(*_args, **_kwargs) -> None:  # type: ignore[misc]
        return None


class LLMUnavailableError(Exception):
    """Raised when the LLM call is unavailable (connection / auth / timeout)."""


def _extract_message_content(message) -> str:
    """Robustly extract text from a response message.

    Why: aggregation gateways may route model=auto requests to a
    "reasoning model" (e.g. step-3.7-flash). Such models put the final answer in
    ``reasoning_content`` rather than ``content`` (which is then None). Reading only
    ``content`` would yield an empty string and make the whole app return blank.
    This is the fallback: when ``content`` is empty we fall back to
    ``reasoning_content`` / ``reasoning``, so "drop in a key and it just works"
    regardless of whether the gateway routes to a reasoning or a normal model.
    """
    content = getattr(message, "content", None)
    if content:
        return content
    for attr in ("reasoning_content", "reasoning"):
        val = getattr(message, attr, None)
        if val:
            return val
    return ""


class LLMClient:
    """Unified LLM client; builds the underlying openai SDK client by provider_type."""

    # 最近一次调用累计的 prompt_tokens / completion_tokens（由 chat() 方法写入，
    # chat handler 的 _build_assistant_message_meta() 与仪表盘 Token 统计消费）。
    _cumulative_prompt_tokens: int = 0
    _cumulative_completion_tokens: int = 0
    _model_name_used: str | None = None

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self.client = self._create_client(config)
        self.last_usage = None  # 最近一次调用的 token 用量（供上层提取）

    @staticmethod
    def _create_client(config: LLMConfig) -> OpenAI:
        """Create an OpenAI-compatible client based on the vendor type."""
        if config.provider_type == "ollama":
            # Local Ollama needs no auth; use a placeholder key to satisfy the SDK.
            return OpenAI(
                base_url=config.base_url or "http://localhost:11434/v1",
                api_key="ollama",
                timeout=_LLM_CALL_TIMEOUT,
                max_retries=0,  # 重试交由 tenacity 统一控制，避免与 SDK 双重重试
            )
        # openai / anthropic / other compatible vendors: use config base_url + api_key.
        return OpenAI(
            base_url=config.base_url,
            api_key=config.api_key or "not-required",
            timeout=_LLM_CALL_TIMEOUT,
            max_retries=0,  # 重试交由 tenacity 统一控制，避免与 SDK 双重重试
        )

    @_llm_retry
    def _chat_completion(self, **kwargs):
        """实际 chat.completions.create 调用，经 tenacity 对瞬态错误重试。

        重试耗尽后抛原始 openai.OpenAIError 子类，由调用方 ``chat`` /
        ``verify_connection`` / ``analyze_image`` 统一捕获并降级。
        """
        return self.client.chat.completions.create(**kwargs)

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2000,
        stop: list[str] | None = None,
        *,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> str:
        """Synchronous chat: returns the full text response, logs latency and token usage.

        Args:
            stop: optional stop sequences. Under ReAct mode pass ``["\\nObservation"]``
                to stop the model from fabricating tool results (Observation is provided
                by the system in the next round).
            tenant_id / user_id: optional subject identifiers for security audit trails
                (backward compatible, default None).
        """
        # Pre-call security gate: prompt-injection detection + audit. On a high-risk
        # injection with blocking enabled it raises InjectionBlockedError, which the
        # caller decides how to surface to the user.
        guard_llm_call(
            system_prompt, user_prompt,
            tenant_id=tenant_id, user_id=user_id, model_name=self.config.model_name,
        )
        start = time.time()
        call_success = True
        call_error = ""
        usage = None
        try:
            try:
                resp = self._chat_completion(
                    model=self.config.model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stop=stop,
                )
            except openai.OpenAIError as exc:
                # Normalize SDK connection / auth / rate-limit errors into our own exception.
                logger.error("LLM call failed: %s", exc)
                call_success = False
                call_error = str(exc)
                if _demo_fallback_enabled():
                    logger.warning(
                        "LLM_DEMO_FALLBACK enabled — returning canned response for failed call "
                        "(model=%s, err=%s)",
                        self.config.model_name, exc,
                    )
                    return _canned_response(system_prompt, user_prompt)
                raise LLMUnavailableError(str(exc)) from exc

            content = _extract_message_content(resp.choices[0].message)
            usage = resp.usage
            self.last_usage = usage  # 供上层（run_agent/chat handler）提取 token 用量
            # 累计到类变量供仪表盘 Token 统计
            if usage:
                LLMClient._cumulative_prompt_tokens += usage.prompt_tokens or 0
                LLMClient._cumulative_completion_tokens += usage.completion_tokens or 0
                LLMClient._model_name_used = self.config.model_name
            logger.info(
                "LLM call done model=%s latency=%.2fs prompt_tokens=%s completion_tokens=%s",
                self.config.model_name,
                time.time() - start,
                usage.prompt_tokens if usage else "N/A",
                usage.completion_tokens if usage else "N/A",
            )
            return content
        finally:
            # best-effort 埋点：记录 llm_call 运行日志
            try:
                from finpilot.services.runtime_log_service import log_runtime
                from finpilot.database import SessionLocal

                _log_db = SessionLocal()
                try:
                    log_runtime(
                        _log_db,
                        category="llm_call",
                        event="llm_response",
                        message=f"LLM call model={self.config.model_name}",
                        source="llm.client.chat",
                        payload={
                            "model": self.config.model_name,
                            "provider_type": self.config.provider_type,
                            "prompt_tokens": usage.prompt_tokens if usage else None,
                            "completion_tokens": usage.completion_tokens if usage else None,
                            "total_tokens": usage.total_tokens if usage else None,
                            "temperature": temperature,
                            "max_tokens": max_tokens,
                            "user_prompt_preview": (user_prompt or "")[:300],
                            "response_preview": (locals().get("content") or "")[:300],
                            "error": call_error or None,
                        },
                        duration_ms=int((time.time() - start) * 1000),
                        tenant_id=tenant_id,
                        user_id=user_id,
                        success=call_success,
                        level="info" if call_success else "error",
                    )
                finally:
                    _log_db.close()
            except Exception:  # noqa: BLE001
                pass

    def chat_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2000,
        *,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> Iterator[str]:
        """Streaming chat: yields text deltas chunk by chunk, then logs total latency and tokens."""
        guard_llm_call(
            system_prompt, user_prompt,
            tenant_id=tenant_id, user_id=user_id, model_name=self.config.model_name,
        )
        try:
            stream = self._chat_completion(
                model=self.config.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
                stream_options={"include_usage": True},
            )
        except openai.OpenAIError as exc:
            logger.error("LLM streaming call failed: %s", exc)
            raise LLMUnavailableError(str(exc)) from exc

        start = time.time()
        total_tokens = 0
        for chunk in stream:
            # The final chunk carries cumulative usage (needs stream_options.include_usage).
            if chunk.usage:
                total_tokens = chunk.usage.total_tokens
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            # Prefer content; streaming deltas from reasoning models may only appear on
            # reasoning_content.
            piece = getattr(delta, "content", None) or getattr(
                delta, "reasoning_content", None
            )
            if piece:
                yield piece
        logger.info(
            "LLM stream done model=%s latency=%.2fs total_tokens=%s",
            self.config.model_name,
            time.time() - start,
            total_tokens or "N/A",
        )

    def verify_connection(self, max_tokens: int = 10) -> None:
        """真实连通性探测：发起一次最小 chat 请求，不启用 demo fallback。

        任何 openai 错误都会被原样抛出为 ``LLMUnavailableError``，调用方可据此
        区分「真实失败」与「成功」。这是 test_provider 端点应该使用的路径，避免
        demo fallback 把 401/网络错误伪装成「连通正常」。
        """
        start = time.time()
        try:
            resp = self._chat_completion(
                model=self.config.model_name,
                messages=[
                    {"role": "system", "content": "你是连通性测试助手。"},
                    {"role": "user", "content": "ping"},
                ],
                temperature=0.0,
                max_tokens=max_tokens,
            )
        except openai.OpenAIError as exc:
            logger.error("LLM verify_connection failed: %s", exc)
            raise LLMUnavailableError(str(exc)) from exc
        logger.info(
            "LLM verify_connection ok model=%s latency=%.2fs",
            self.config.model_name,
            time.time() - start,
        )
        # 触发一次 message 提取，确保响应可用
        _extract_message_content(resp.choices[0].message)

    def analyze_image(self, image_base64: str, prompt: str) -> str:
        """Multimodal image analysis: sends a base64 image plus a prompt to a vision model."""
        start = time.time()
        try:
            resp = self._chat_completion(
                model=self.config.model_name,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{image_base64}",
                                },
                            },
                        ],
                    },
                ],
                temperature=0.3,
                max_tokens=2000,
            )
        except openai.OpenAIError as exc:
            logger.error("LLM image analysis failed: %s", exc)
            raise LLMUnavailableError(str(exc)) from exc

        content = _extract_message_content(resp.choices[0].message)
        usage = resp.usage
        logger.info(
            "LLM image analysis done model=%s latency=%.2fs total_tokens=%s",
            self.config.model_name,
            time.time() - start,
            usage.total_tokens if usage else "N/A",
        )
        return content
