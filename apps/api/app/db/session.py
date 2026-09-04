"""按配置连接本地或远程库，支持运行中切换。"""

import gc
import os
import time
from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.core.config import get_settings
from app.core.local_settings import get_effective_database_url

Base = declarative_base()


class _Db:
    engine: Engine | None = None
    SessionLocal: sessionmaker | None = None
    url: str = ""


def _engine_kwargs(url: str) -> dict:
    kwargs: dict = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs["pool_recycle"] = 3600
    return kwargs


def dispose_database() -> None:
    """先断开，才能搬本地库文件。"""

    if _Db.engine is not None:
        _Db.engine.dispose()
        _Db.engine = None
        _Db.SessionLocal = None
        _Db.url = ""
    gc.collect()
    if os.name == "nt":
        time.sleep(0.3)


def connect_database(url: str) -> None:
    """换到新连接，并按模型建表。"""

    if _Db.engine is not None:
        _Db.engine.dispose()
    _Db.url = url
    _Db.engine = create_engine(url, **_engine_kwargs(url))
    _Db.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_Db.engine)
    from app.portal.models import PortalLink  # noqa: F401
    from app.resume.models import ResumeDoc, ResumeInterview, ResumeInterviewMessage  # noqa: F401
    from app.wardrobe.models import WardrobeItem, WardrobeLook, WardrobeStyle  # noqa: F401
    from app.kb.models import KbChunk, KbDocument, KbFolder, KbLibrary  # noqa: F401

    Base.metadata.create_all(bind=_Db.engine)
    _ensure_resume_columns(_Db.engine)
    _ensure_portal_columns(_Db.engine)
    _ensure_kb_columns(_Db.engine)


def _ensure_resume_columns(engine: Engine) -> None:
    """旧库补上简历自我介绍字段，避免只建新表不改旧表。"""

    inspector = inspect(engine)
    if "resume_docs" not in inspector.get_table_names():
        return
    cols = {item["name"] for item in inspector.get_columns("resume_docs")}
    if "intro" in cols:
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE resume_docs ADD COLUMN intro TEXT DEFAULT ''"))


def _ensure_portal_columns(engine: Engine) -> None:
    """旧库补上入口分类字段。"""

    inspector = inspect(engine)
    if "portal_links" not in inspector.get_table_names():
        return
    cols = {item["name"] for item in inspector.get_columns("portal_links")}
    if "category" in cols:
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE portal_links ADD COLUMN category VARCHAR(80) DEFAULT ''"))


def _ensure_kb_columns(engine: Engine) -> None:
    """旧库补上知识库检索正文。"""

    inspector = inspect(engine)
    if "kb_documents" not in inspector.get_table_names():
        return
    cols = {item["name"] for item in inspector.get_columns("kb_documents")}
    if "search_text" in cols:
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE kb_documents ADD COLUMN search_text TEXT DEFAULT ''"))


def try_connect(url: str) -> tuple[bool, str]:
    """只探测，不切换当前连接。"""

    engine = create_engine(url, **_engine_kwargs(url))
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, ""
    except Exception as exc:
        return False, str(exc)
    finally:
        engine.dispose()


def init_database() -> None:
    settings = get_settings()
    connect_database(get_effective_database_url(settings.database_url, settings.repo_root))


def get_database_url() -> str:
    return _Db.url


def get_engine() -> Engine:
    if _Db.engine is None:
        init_database()
    assert _Db.engine is not None
    return _Db.engine


def get_db() -> Generator[Session, None, None]:
    """提供一次数据库会话。"""

    if _Db.SessionLocal is None:
        init_database()
    assert _Db.SessionLocal is not None
    db = _Db.SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ping_database() -> tuple[bool, str]:
    """探测当前库是否通。"""

    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, ""
    except Exception as exc:
        return False, str(exc)


# 兼容旧引用
engine = None
