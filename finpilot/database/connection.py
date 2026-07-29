"""
数据库连接模块 - SQLite 数据层
- 数据库路径：~/.finpilot/finpilot.db（自动创建目录）
- 提供 engine、SessionLocal、init_db()、get_db()
"""
import logging
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

logger = logging.getLogger(__name__)

# SQLite 数据库路径：~/.finpilot/finpilot.db，自动创建目录
DB_DIR = Path.home() / ".finpilot"
DB_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_PATH = DB_DIR / "finpilot.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

# 创建引擎；SQLite 多线程需关闭 check_same_thread，StaticPool 保证连接复用
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    echo=False,
)

# 会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# 板块D + 迁移 e1f2a3b4c5d6 + c2f3a4b5c6d7：为已有表补列的幂等补丁。
# create_all 只建缺失的表，不会给已存在的表加列；这里用 ALTER TABLE 兜底，
# 让老库升级时也能拿到所有迁移引入的新列。
# 注意：类型变更（如 String→Integer）无法通过 ADD COLUMN 解决，需 alembic batch 重建表。
# 每个条目: (表名, 列名, SQLite DDL 片段)
_SCHEMA_PATCH_COLUMNS: list[tuple[str, str, str]] = [
    # === 迁移 d3a4b5c6d7e8（板块D）===
    # AgentConfig: agent_type / prompt_id / max_iterations / temperature
    ("agent_configs", "agent_type", "VARCHAR(32) DEFAULT 'react' NOT NULL"),
    ("agent_configs", "prompt_id", "INTEGER"),
    ("agent_configs", "max_iterations", "INTEGER DEFAULT 10 NOT NULL"),
    ("agent_configs", "temperature", "FLOAT DEFAULT 0.7 NOT NULL"),
    # LlmProvider: updated_at
    ("llm_providers", "updated_at", "DATETIME"),
    # LlmModel: parameters
    ("llm_models", "parameters", "JSON"),
    # SearchEngine: tenant_id / extra_params / priority
    ("search_engines", "tenant_id", "VARCHAR(100)"),
    ("search_engines", "extra_params", "JSON"),
    ("search_engines", "priority", "INTEGER DEFAULT 0 NOT NULL"),
    # === 迁移 e1f2a3b4c5d6（repair_causal_chain）===
    # api_keys: scopes
    ("api_keys", "scopes", "TEXT"),
    # financial_reports: document_id / tenant_id
    ("financial_reports", "document_id", "INTEGER"),
    ("financial_reports", "tenant_id", "VARCHAR(100)"),
    # reports: document_id / data_connection_id
    # 注意：reports.template_id 的 String→Integer 类型变更无法通过 ADD COLUMN 处理，
    # 需 alembic batch_alter_table；这里仅补缺失列。
    ("reports", "document_id", "INTEGER"),
    ("reports", "data_connection_id", "INTEGER"),
    # audit_logs: target_object_type / target_object_id / resource / ip_address
    ("audit_logs", "target_object_type", "VARCHAR(32)"),
    ("audit_logs", "target_object_id", "VARCHAR(64)"),
    ("audit_logs", "resource", "VARCHAR(255)"),
    ("audit_logs", "ip_address", "VARCHAR(64)"),
    # conversations: agent_config_id
    ("conversations", "agent_config_id", "INTEGER"),
    # messages: model_name / tokens_in / tokens_out / latency_ms / tool_calls
    ("messages", "model_name", "VARCHAR(200)"),
    ("messages", "tokens_in", "INTEGER"),
    ("messages", "tokens_out", "INTEGER"),
    ("messages", "latency_ms", "INTEGER"),
    ("messages", "tool_calls", "TEXT"),
    # === 迁移 c2f3a4b5c6d7（section_c_frontend_routes）===
    # api_keys 扩展：tenant_id / key_prefix / first_used_at / usage_count / expires_at / rotated_from / updated_at
    ("api_keys", "tenant_id", "VARCHAR(100)"),
    ("api_keys", "key_prefix", "VARCHAR(32)"),
    ("api_keys", "first_used_at", "DATETIME"),
    ("api_keys", "usage_count", "INTEGER DEFAULT 0"),
    ("api_keys", "expires_at", "DATETIME"),
    ("api_keys", "rotated_from", "INTEGER"),
    ("api_keys", "updated_at", "DATETIME"),
]


def _apply_schema_patches() -> None:
    """幂等给已存在的表补齐新列（SQLite ALTER TABLE ADD COLUMN）."""
    try:
        insp = inspect(engine)
        with engine.begin() as conn:
            for table, column, ddl in _SCHEMA_PATCH_COLUMNS:
                if not insp.has_table(table):
                    continue
                existing = {c["name"] for c in insp.get_columns(table)}
                if column not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
    except Exception as exc:  # noqa: BLE001
        # 补丁失败不应阻断启动（最坏只是新字段读不到，回到旧行为）
        logger.warning("schema_patches 跳过: %s", exc)


def init_db() -> None:
    """创建所有数据库表，并补齐已有表的新列."""
    # 延迟导入避免循环依赖，同时触发所有模型注册到 Base.metadata
    from . import models  # noqa: F401
    from .models import Base

    Base.metadata.create_all(bind=engine)
    _apply_schema_patches()
    logger.info("数据库已初始化：%s", DATABASE_PATH)


def get_db():
    """FastAPI 依赖注入：获取数据库会话，请求结束后自动关闭"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
