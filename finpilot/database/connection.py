"""
数据库连接模块 - SQLite 数据层
- 数据库路径：~/.finpilot/finpilot.db（自动创建目录）
- 提供 engine、SessionLocal、init_db()、get_db()
"""
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

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


def init_db() -> None:
    """创建所有数据库表"""
    # 延迟导入避免循环依赖，同时触发所有模型注册到 Base.metadata
    from . import models  # noqa: F401
    from .models import Base

    Base.metadata.create_all(bind=engine)
    print(f"数据库已初始化：{DATABASE_PATH}")


def get_db():
    """FastAPI 依赖注入：获取数据库会话，请求结束后自动关闭"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
