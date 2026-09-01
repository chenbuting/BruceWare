"""设置：查看并切换本地 / 远程数据源。"""

from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.config import describe_database, get_settings
from app.core.local_settings import (
    build_database_url,
    get_effective_database_url,
    load_local_settings,
    parse_database_form,
    save_local_settings,
)
from app.core.response import fail, ok
from app.db.session import connect_database, get_database_url, ping_database, try_connect

router = APIRouter()


class DatabaseForm(BaseModel):
    """设置页提交的数据源表单。"""

    mode: Literal["local", "mysql", "postgres"]
    sqlite_path: str = "./data/bruceware.db"
    host: str = ""
    port: int | None = None
    name: str = ""
    user: str = ""
    password: str = Field(default="", description="留空表示不改原密码")


def _settings_payload() -> dict[str, Any]:
    settings = get_settings()
    url = get_database_url() or get_effective_database_url(settings.database_url, settings.repo_root)
    connected, error = ping_database()
    stored = load_local_settings(settings.repo_root).get("database") or {}
    db = describe_database(url)
    return {
        "app_name": settings.app_name,
        "api_host": settings.api_host,
        "api_port": settings.api_port,
        "database": {
            **db,
            "connected": connected,
            "error": error,
            "form": parse_database_form(url, stored if isinstance(stored, dict) else {}),
        },
    }


@router.get("/settings")
def read_settings():
    """当前配置，密码不返回。"""

    return ok(_settings_payload())


def _prepare_url(form: DatabaseForm) -> tuple[str, str] | Any:
    from app.core.config import resolve_database_url

    settings = get_settings()
    stored = load_local_settings(settings.repo_root).get("database") or {}
    old_password = str(stored.get("password") or "") if isinstance(stored, dict) else ""
    try:
        url = build_database_url(form.model_dump(), old_password)
    except ValueError as exc:
        return fail(str(exc))
    return url, resolve_database_url(url, settings.repo_root)


@router.post("/settings/test-database")
def test_database(form: DatabaseForm):
    """只测试，不切换。"""

    prepared = _prepare_url(form)
    if not isinstance(prepared, tuple):
        return prepared
    _, resolved = prepared
    ok_conn, error = try_connect(resolved)
    if not ok_conn:
        return fail(f"连不上：{error}")
    return ok({"connected": True})


@router.put("/settings/database")
def save_database(form: DatabaseForm):
    """测试通过后写入本机设置并切换。"""

    prepared = _prepare_url(form)
    if not isinstance(prepared, tuple):
        return prepared
    raw_url, resolved = prepared
    ok_conn, error = try_connect(resolved)
    if not ok_conn:
        return fail(f"连不上，未保存：{error}")

    settings = get_settings()
    existing = load_local_settings(settings.repo_root)
    stored = existing.get("database") if isinstance(existing.get("database"), dict) else {}
    password = form.password or str(stored.get("password") or "")
    existing["database"] = {
        "mode": form.mode,
        "url": raw_url,
        "sqlite_path": form.sqlite_path,
        "host": form.host,
        "port": form.port,
        "name": form.name,
        "user": form.user,
        "password": password,
    }
    save_local_settings(settings.repo_root, existing)
    connect_database(resolved)
    return ok(_settings_payload())
