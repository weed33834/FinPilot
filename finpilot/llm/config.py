"""
LLM 多供应商配置层
- 从数据库读取供应商/模型配置，支持 60 秒 TTL 缓存
- 环境变量作为 DB 缺失时的回退（优先级低于 DB 配置）
"""
import os
import time
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from finpilot.database.crud import decode_api_key
from finpilot.database.models import LlmModel, LlmProvider

# 缓存 TTL（秒）
_CACHE_TTL = 60
# 模块级缓存：缓存键 -> (写入时间戳, LLMConfig)
_cache: dict[str, tuple[float, "LLMConfig"]] = {}


@dataclass
class LLMConfig:
    """LLM 调用配置 - 描述一次调用所需的全部连接信息"""
    provider_type: str            # openai/anthropic/ollama
    base_url: Optional[str]       # API 基地址
    api_key: Optional[str]        # 明文 API key（已从 base64 解码）
    model_name: str               # 调用接口用的模型标识
    tier: str = "medium"          # 性能层级 low/medium/high


def invalidate_cache() -> None:
    """主动清空全部配置缓存（供应商/模型变更后调用）"""
    _cache.clear()


def _is_expired(timestamp: float) -> bool:
    """判断缓存条目是否已超过 TTL"""
    return time.time() - timestamp > _CACHE_TTL


def _build_config_from_provider(provider: LlmProvider, model: LlmModel) -> LLMConfig:
    """根据供应商与模型记录构建 LLMConfig，解码 base64 存储的 api_key"""
    api_key = None
    if provider.api_key:
        try:
            api_key = decode_api_key(provider.api_key)
        except ValueError:
            # 存储值非合法 base64 时按明文兜底，避免阻断配置加载
            api_key = provider.api_key
    return LLMConfig(
        provider_type=provider.provider_type,
        base_url=provider.base_url,
        api_key=api_key,
        model_name=model.model_name,
        tier=model.tier,
    )


def _fallback_from_env() -> Optional[LLMConfig]:
    """DB 无配置时从环境变量回退构建配置（优先级低于 DB）"""
    # OpenAI 回退
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        return LLMConfig(
            provider_type="openai",
            base_url=os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1",
            api_key=openai_key,
            model_name=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            tier="medium",
        )
    # Anthropic 回退
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    if anthropic_key:
        return LLMConfig(
            provider_type="anthropic",
            base_url=os.getenv("ANTHROPIC_BASE_URL") or "https://api.anthropic.com/v1",
            api_key=anthropic_key,
            model_name=os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022"),
            tier="medium",
        )
    return None


def _load_default_from_db(db: Session) -> Optional[LLMConfig]:
    """从 DB 读取默认供应商下首个激活模型的配置"""
    provider = (
        db.query(LlmProvider)
        .filter(LlmProvider.is_default.is_(True), LlmProvider.is_active.is_(True))
        .first()
    )
    if not provider:
        return None
    model = (
        db.query(LlmModel)
        .filter(LlmModel.provider_id == provider.id, LlmModel.is_active.is_(True))
        .first()
    )
    if not model:
        return None
    return _build_config_from_provider(provider, model)


def _load_tier_from_db(db: Session, tier: str) -> Optional[LLMConfig]:
    """从 DB 读取指定层级模型的供应商配置"""
    model = (
        db.query(LlmModel)
        .filter(LlmModel.tier == tier, LlmModel.is_active.is_(True))
        .first()
    )
    if not model:
        return None
    provider = db.get(LlmProvider, model.provider_id)
    if not provider or not provider.is_active:
        return None
    return _build_config_from_provider(provider, model)


def get_default_config(db: Session) -> Optional[LLMConfig]:
    """获取默认供应商配置（DB 优先，环境变量回退），带 60s TTL 缓存"""
    cache_key = "default"
    cached = _cache.get(cache_key)
    if cached and not _is_expired(cached[0]):
        return cached[1]

    # DB 配置优先级高于环境变量
    config = _load_default_from_db(db)
    if config is None:
        config = _fallback_from_env()

    if config is not None:
        _cache[cache_key] = (time.time(), config)
    return config


def get_tier_config(db: Session, tier: str) -> Optional[LLMConfig]:
    """按性能层级获取配置（DB 优先，环境变量回退），带 60s TTL 缓存"""
    cache_key = f"tier:{tier}"
    cached = _cache.get(cache_key)
    if cached and not _is_expired(cached[0]):
        return cached[1]

    # DB 配置优先级高于环境变量
    config = _load_tier_from_db(db, tier)
    if config is None:
        config = _fallback_from_env()

    if config is not None:
        _cache[cache_key] = (time.time(), config)
    return config
