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


# 板块D：为已有表补列的幂等补丁。
# create_all 只建缺失的表，不会给已存在的表加列；这里用 ALTER TABLE 兜底，
# 让老库升级时也能拿到 agent_configs / llm_models / llm_providers / search_engines 的新列。
# 每个条目: (表名, 列名, SQLite DDL 片段)
_SCHEMA_PATCH_COLUMNS: list[tuple[str, str, str]] = [
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
