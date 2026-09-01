"""本机设置文件。数据源配置放这里，不进远程库。"""

import json
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlparse, unquote

from app.core.config import resolve_database_url


def settings_file(repo_root: Path) -> Path:
    return repo_root / "data" / "app-settings.json"


def load_local_settings(repo_root: Path) -> dict[str, Any]:
    path = settings_file(repo_root)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_local_settings(repo_root: Path, data: dict[str, Any]) -> None:
    path = settings_file(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_effective_database_url(env_url: str, repo_root: Path) -> str:
    """界面保存过的库优先，否则用 .env。"""

    stored = (load_local_settings(repo_root).get("database") or {})
    raw = str(stored.get("url") or env_url)
    return resolve_database_url(raw, repo_root)


def default_port(mode: str) -> int:
    return 5432 if mode == "postgres" else 3306


def build_database_url(form: dict[str, Any], old_password: str = "") -> str:
    """把设置表单拼成连接串。密码留空则沿用旧密码。"""

    mode = form.get("mode") or "local"
    if mode == "local":
        path = str(form.get("sqlite_path") or "./data/bruceware.db").strip()
        if not path:
            raise ValueError("请填写本地库路径")
        return f"sqlite:///{path}"

    host = str(form.get("host") or "").strip()
    name = str(form.get("name") or "").strip()
    user = str(form.get("user") or "").strip()
    if not host or not name or not user:
        raise ValueError("远程库请填写主机、库名、用户名")

    port = form.get("port")
    if not port:
        port = default_port(mode)
    password = str(form.get("password") or "") or old_password
    user_q = quote_plus(user)
    pwd_q = quote_plus(password)
    if mode == "mysql":
        return f"mysql+pymysql://{user_q}:{pwd_q}@{host}:{int(port)}/{name}"
    if mode == "postgres":
        return f"postgresql+psycopg://{user_q}:{pwd_q}@{host}:{int(port)}/{name}"
    raise ValueError("不支持的数据源类型")


def parse_database_form(url: str, stored: dict[str, Any] | None = None) -> dict[str, Any]:
    """给设置页回填，不含密码。"""

    stored = stored or {}
    if stored.get("mode"):
        mode = str(stored.get("mode"))
        return {
            "mode": mode,
            "sqlite_path": str(stored.get("sqlite_path") or "./data/bruceware.db"),
            "host": str(stored.get("host") or ""),
            "port": int(stored.get("port") or default_port(mode)),
            "name": str(stored.get("name") or ""),
            "user": str(stored.get("user") or ""),
            "has_password": bool(stored.get("password") or ""),
        }

    if url.startswith("sqlite"):
        return {
            "mode": "local",
            "sqlite_path": url.replace("sqlite:///", "", 1),
            "host": "",
            "port": 3306,
            "name": "",
            "user": "",
            "has_password": False,
        }

    parsed = urlparse(
        url.replace("mysql+pymysql://", "mysql://", 1).replace("postgresql+psycopg://", "postgresql://", 1)
    )
    mode = "mysql" if parsed.scheme.startswith("mysql") else "postgres"
    return {
        "mode": mode,
        "sqlite_path": "./data/bruceware.db",
        "host": parsed.hostname or "",
        "port": parsed.port or default_port(mode),
        "name": (parsed.path or "").lstrip("/"),
        "user": unquote(parsed.username or ""),
        "has_password": bool(parsed.password),
    }
