"""联网搜索内置工具 — web_search + fetch_url。

读取管理后台 ``SearchEngine`` 配置表（按 tenant_id 隔离、is_default/is_active 过滤、
priority 升序），真实发起搜索请求并把结果摘要返回给 ReAct。

支持的后端：
    - serpapi:  调 https://serpapi.com/search（需 api_key）
    - bing:     调 Bing Web Search API v7（需 api_key，header Ocp-Apim-Subscription-Key）
    - google:   调 Google Custom Search JSON API（需 api_key + extra_params.cx）
    - custom:   通用 JSON 搜索接口，base_url + api_key（query 参数名默认 q）

所有工具失败均返回 ``{"error": "..."}``，由 ReAct guardrails 引导 LLM 自纠，
不抛异常打断图执行。
"""
from __future__ import annotations

from typing import Any, Optional

import requests

from .tool_registry import ToolContext, tool_registry

# 单次网页正文抓取的字符上限，避免上下文爆炸
_MAX_FETCH_CHARS = 4000
# 单条搜索结果摘要长度
_SNIPPET_LEN = 300
# 请求超时（秒）
_HTTP_TIMEOUT = 10


def _pick_search_engine(ctx: ToolContext) -> Optional[Any]:
    """从 DB 选取当前租户可用的默认/最高优先级 SearchEngine。

    返回 SearchEngine ORM 对象或 None（无配置时）。
    """
    if ctx.db is None:
        return None
    try:
        from finpilot.database.models import SearchEngine
    except Exception:  # noqa: BLE001
        return None
    q = (
        ctx.db.query(SearchEngine)
        .filter(SearchEngine.is_active.is_(True))
        .filter(SearchEngine.tenant_id == ctx.tenant_id)
        .order_by(SearchEngine.is_default.desc(), SearchEngine.priority.asc())
    )
    return q.first()


def _decode_key(api_key: Optional[str]) -> str:
    """解密 SearchEngine.api_key（Fernet 存储）；失败回退原值。"""
    if not api_key:
        return ""
    try:
        from finpilot.database.crud import decode_api_key

        return decode_api_key(api_key)
    except Exception:  # noqa: BLE001
        return api_key


def _run_search(se: Any, query: str, max_results: int) -> list[dict[str, str]]:
    """按 engine_type 分发，返回归一化结果列表 [{title, url, snippet}]。"""
    engine_type = (se.engine_type or "custom").lower()
    base_url = (se.base_url or "").strip()
    api_key = _decode_key(se.api_key)
    extra = se.extra_params or {}
    limit = max_results or se.max_results or 8

    results: list[dict[str, str]] = []

    try:
        if engine_type == "serpapi" and base_url:
            params = {
                "q": query,
                "api_key": api_key,
                "num": limit,
                "engine": extra.get("engine", "google"),
            }
            resp = requests.get(base_url, params=params, timeout=_HTTP_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            for item in (data.get("organic_results") or [])[:limit]:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "snippet": (item.get("snippet") or "")[:_SNIPPET_LEN],
                })

        elif engine_type == "bing":
            endpoint = base_url or "https://api.bing.microsoft.com/v7.0/search"
            headers = {"Ocp-Apim-Subscription-Key": api_key}
            params = {"q": query, "count": limit}
            resp = requests.get(endpoint, headers=headers, params=params, timeout=_HTTP_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            for item in (data.get("webPages", {}).get("value") or [])[:limit]:
                results.append({
                    "title": item.get("name", ""),
                    "url": item.get("url", ""),
                    "snippet": (item.get("snippet") or "")[:_SNIPPET_LEN],
                })

        elif engine_type == "google":
            cx = extra.get("cx", "")
            endpoint = base_url or "https://www.googleapis.com/customsearch/v1"
            params = {"q": query, "key": api_key, "cx": cx, "num": limit}
            resp = requests.get(endpoint, params=params, timeout=_HTTP_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            for item in (data.get("items") or [])[:limit]:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "snippet": (item.get("snippet") or "")[:_SNIPPET_LEN],
                })

        else:
            # custom：通用 JSON 接口，query 参数名取 extra_params.query_param，默认 q
            if not base_url:
                return [{"error": "custom 引擎未配置 base_url"}]
            qp = extra.get("query_param", "q")
            params = {qp: query, "count": limit}
            headers = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            resp = requests.get(base_url, headers=headers, params=params, timeout=_HTTP_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            # 宽松解析：尝试常见字段
            items = (
                data.get("results")
                or data.get("items")
                or data.get("organic_results")
                or data.get("data")
                or []
            )
            if isinstance(items, list):
                for item in items[:limit]:
                    if not isinstance(item, dict):
                        continue
                    results.append({
                        "title": item.get("title") or item.get("name") or "",
                        "url": item.get("url") or item.get("link") or "",
                        "snippet": (item.get("snippet") or item.get("description") or "")[:_SNIPPET_LEN],
                    })
    except requests.RequestException as exc:
        return [{"error": f"搜索请求失败：{exc}"}]
    except Exception as exc:  # noqa: BLE001
        return [{"error": f"搜索解析失败：{exc}"}]

    return results


@tool_registry.register(
    name="web_search",
    description=(
        "联网搜索：根据查询词调用配置的搜索引擎（SerpAPI/Bing/Google/Custom），"
        "返回标题、链接与摘要列表。用于获取实时信息、最新新闻、公开数据等知识库外内容。"
    ),
    parameters_schema={"query": "str,必填,搜索查询词"},
    tags=["web", "search"],
)
def web_search(ctx: ToolContext, **kwargs: Any) -> dict:
    query = (kwargs.get("query") or "").strip()
    if not query:
        return {"error": "缺少参数: query"}

    se = _pick_search_engine(ctx)
    if se is None:
        return {"error": "未配置可用的搜索引擎，请联系管理员在「搜索引擎」页面添加并启用"}

    results = _run_search(se, query, se.max_results or 8)
    # 过滤错误项单独提示
    errors = [r for r in results if "error" in r]
    clean = [r for r in results if "error" not in r]

    if not clean:
        return {
            "error": errors[0]["error"] if errors else "搜索未返回任何结果",
            "engine": se.engine_type,
            "query": query,
        }

    return {
        "query": query,
        "engine": se.engine_type,
        "result_count": len(clean),
        "results": clean,
        # 文本摘要供 ReAct 直接消费（LLM 不需解析结构化列表）
        "summary": "\n".join(
            f"{i + 1}. {r['title']}\n   {r['url']}\n   {r['snippet']}"
            for i, r in enumerate(clean)
        ),
    }


@tool_registry.register(
    name="fetch_url",
    description=(
        "抓取指定网页正文内容并返回纯文本摘要（去标签、限长）。"
        "用于在 web_search 找到相关链接后深入阅读具体页面内容。"
    ),
    parameters_schema={"url": "str,必填,要抓取的网页 URL"},
    tags=["web", "fetch"],
)
def fetch_url(ctx: ToolContext, **kwargs: Any) -> dict:
    url = (kwargs.get("url") or "").strip()
    if not url:
        return {"error": "缺少参数: url"}
    if not url.startswith(("http://", "https://")):
        return {"error": "URL 必须以 http:// 或 https:// 开头"}

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; FinPilotBot/2.0)",
            "Accept": "text/html,application/xhtml+xml",
        }
        resp = requests.get(url, headers=headers, timeout=_HTTP_TIMEOUT, allow_redirects=True)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "")
        raw = resp.text or ""
    except requests.RequestException as exc:
        return {"error": f"抓取失败：{exc}"}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"抓取异常：{exc}"}

    text = _extract_text(raw, content_type)
    # 统一截断，避免超长正文撑爆 LLM 上下文
    if len(text) > _MAX_FETCH_CHARS:
        text = text[:_MAX_FETCH_CHARS] + "\n\n...(内容已截断)"

    return {
        "url": url,
        "content_type": content_type,
        "title": _extract_title(raw),
        "text": text,
        "length": len(text),
    }


def _extract_text(html: str, content_type: str) -> str:
    """从 HTML 中粗提取正文文本（轻量去标签，不依赖 bs4）。"""
    import re

    # 非 HTML 直接返回
    if "html" not in content_type.lower() and "<" not in html:
        return html

    # 移除 script/style/noscript 块
    cleaned = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", "", html, flags=re.S | re.I)
    # 移除所有标签
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    # HTML 实体转义还原
    entities = {
        "&nbsp;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">",
        "&quot;": '"', "&#39;": "'", "&apos;": "'",
    }
    for k, v in entities.items():
        cleaned = cleaned.replace(k, v)
    # 压缩空白
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _extract_title(html: str) -> str:
    """从 HTML 提取 <title> 内容。"""
    import re

    m = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.S | re.I)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip()
    return ""
