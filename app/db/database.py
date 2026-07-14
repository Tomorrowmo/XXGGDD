"""SQLAlchemy 引擎 / 会话 / 建表。默认 SQLite，可经 EVAL_DB_URL 换 Postgres。"""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

from app.settings import settings


class Base(DeclarativeBase):
    pass


_connect_args = {"check_same_thread": False} if settings.db_url.startswith("sqlite") else {}
engine = create_engine(settings.db_url, echo=False, future=True, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：请求级会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """建表（幂等）。启动时调用。"""
    settings.ensure_dirs()
    from app.db import models  # noqa: F401  确保模型已注册到 Base.metadata
    Base.metadata.create_all(bind=engine)
