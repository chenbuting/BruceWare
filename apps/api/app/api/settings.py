"""设置：查看并切换本地 / 远程数据源。"""

import os
import string
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.ai import chat_complete, llm_public
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
    stored = load_local_settings(settings.repo_root)
    db_stored = stored.get("database") or {}
    files_stored = stored.get("files") if isinstance(stored.get("files"), dict) else {}
    files_root = str(files_stored.get("root") or "").strip()
    db = describe_database(url)
    return {
        "app_name": settings.app_name,
        "api_host": settings.api_host,
        "api_port": settings.api_port,
        "database": {
            **db,
            "connected": connected,
            "error": error,
            "form": parse_database_form(url, db_stored if isinstance(db_stored, dict) else {}),
        },
        "llm": llm_public(),
        "files": {
            "root": files_root,
            "ready": bool(files_root) and Path(files_root).expanduser().is_dir(),
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


class LlmForm(BaseModel):
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    image_base_url: str = ""
    image_model: str = "gpt-image-1"
    api_key: str = Field(default="", description="留空表示不改原 Key")
    image_api_key: str = Field(default="", description="留空表示不改原生图 Key")


@router.put("/settings/llm")
def save_llm(form: LlmForm):
    """保存 AI 接口，Key 留空则沿用原来的。"""

    settings = get_settings()
    existing = load_local_settings(settings.repo_root)
    old = existing.get("llm") if isinstance(existing.get("llm"), dict) else {}
    key = form.api_key.strip() or str(old.get("api_key") or "")
    image_key = form.image_api_key.strip() or str(old.get("image_api_key") or "")
    existing["llm"] = {
        "base_url": form.base_url.strip() or "https://api.openai.com/v1",
        "model": form.model.strip() or "gpt-4o-mini",
        "image_base_url": form.image_base_url.strip(),
        "image_model": form.image_model.strip() or "gpt-image-1",
        "api_key": key,
        "image_api_key": image_key,
    }
    save_local_settings(settings.repo_root, existing)
    return ok(_settings_payload())


@router.post("/settings/test-llm")
def test_llm():
    """发一句测试，看 AI 能不能用。"""

    try:
        text = chat_complete(
            [{"role": "user", "content": "只回复两个字：成功"}],
            timeout=30,
        )
    except ValueError as exc:
        return fail(str(exc))
    return ok({"reply": text})


class FilesForm(BaseModel):
    root: str = ""


def _windows_drives() -> list[Path]:
    if hasattr(os, "listdrives"):
        return [Path(item) for item in os.listdrives()]
    found: list[Path] = []
    for letter in string.ascii_uppercase:
        path = Path(f"{letter}:/")
        if path.exists():
            found.append(path)
    return found


def _folder_name(path: Path) -> str:
    text = path.name
    if text:
        return text
    drive = path.drive
    return f"{drive}\\" if drive else str(path)


@router.get("/settings/files/browse")
def browse_folders(path: str = ""):
    """列出本机文件夹，给设置页点选根目录。"""

    raw = path.strip()
    if not raw:
        drives = _windows_drives() if os.name == "nt" else [Path("/")]
        return ok(
            {
                "path": "",
                "parent": "",
                "crumbs": [{"name": "此电脑" if os.name == "nt" else "根目录", "path": ""}],
                "folders": [{"name": _folder_name(item), "path": str(item)} for item in drives],
            }
        )
    current = Path(raw).expanduser()
    if not current.exists() or not current.is_dir():
        return fail("这个文件夹打不开")
    current = current.resolve()
    crumbs = [{"name": "此电脑" if os.name == "nt" else "根目录", "path": ""}]
    if current.drive:
        crumbs.append({"name": f"{current.drive}\\", "path": str(Path(current.anchor))})
    walked = Path(current.anchor) if current.anchor else Path("/")
    for part in current.parts[1:]:
        walked = walked / part
        crumbs.append({"name": part, "path": str(walked)})
    parent = ""
    if current.parent != current:
        parent = str(current.parent)
        if current.drive and current == Path(current.anchor):
            parent = ""
    folders: list[dict[str, str]] = []
    try:
        children = sorted(current.iterdir(), key=lambda item: item.name.lower())
    except OSError:
        return fail("没有权限看这个文件夹")
    for child in children:
        try:
            if child.is_dir():
                folders.append({"name": child.name, "path": str(child)})
        except OSError:
            continue
    return ok({"path": str(current), "parent": parent, "crumbs": crumbs, "folders": folders})


@router.put("/settings/files")
def save_files(form: FilesForm):
    """保存文件柜根目录，文件夹必须已经存在。"""

    raw = form.root.strip()
    if not raw:
        return fail("请填写根目录")
    path = Path(raw).expanduser()
    if not path.exists():
        return fail("这个文件夹不存在")
    if not path.is_dir():
        return fail("必须是文件夹")
    settings = get_settings()
    existing = load_local_settings(settings.repo_root)
    existing["files"] = {"root": str(path)}
    save_local_settings(settings.repo_root, existing)
    return ok(_settings_payload())
