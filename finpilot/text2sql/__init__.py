# -*- coding: utf-8 -*-
"""
FinPilot NL2SQL 双引擎模块
- 规则引擎 + LLM 双引擎生成 SQL
- sqlglot AST 安全沙箱校验
"""
from .engine import NL2SQLEngine, NL2SQLResult
from .sandbox import SQLSandbox
from .schema import (
    FINANCIAL_TABLES,
    METRIC_TO_COLUMN,
    DERIVED_METRICS,
    build_schema_context,
    extract_year,
    extract_period,
)
from .rule_engine import RuleBasedEngine
from .llm_engine import LLMEngine

__all__ = [
    "NL2SQLEngine",
    "NL2SQLResult",
    "SQLSandbox",
    "RuleBasedEngine",
    "LLMEngine",
    "FINANCIAL_TABLES",
    "METRIC_TO_COLUMN",
    "DERIVED_METRICS",
    "build_schema_context",
    "extract_year",
    "extract_period",
]
