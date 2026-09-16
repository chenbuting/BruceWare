"""网盘账号存在本机设置里，令牌不进 git。"""

from __future__ import annotations

import uuid
from typing import Any

from app.core.config import get_settings
from app.core.local_settings import load_local_settings, save_local_settings
from app.drive.kinds import kind_label, kind_ready


def _repo_root():
    return get_settings().repo_root


def _bundle() -> dict[str, Any]:
    stored = load_local_settings(_repo_root())
    raw = stored.get("drive")
    return raw if isinstance(raw, dict) else {}


def _save_bundle(bundle: dict[str, Any]) -> None:
    stored = load_local_settings(_repo_root())
    stored["drive"] = bundle
    save_local_settings(_repo_root(), stored)


def list_raw() -> list[dict[str, Any]]:
    items = _bundle().get("accounts")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict) and item.get("id")]


def get_raw(account_id: str) -> dict[str, Any] | None:
    for item in list_raw():
        if str(item.get("id")) == account_id:
            return item
    return None


def public_account(row: dict[str, Any]) -> dict[str, Any]:
    kind = str(row.get("kind") or "")
    ready = kind_ready(kind)
    authorized = bool(row.get("access_token"))
    message = ""
    if not ready:
        message = "这种网盘以后再接"
    elif not row.get("app_key"):
        message = "请先填 AppKey 和 SecretKey"
    elif not authorized:
        message = "还没授权"
    return {
        "id": str(row.get("id") or ""),
        "kind": kind,
        "kind_label": kind_label(kind),
        "name": str(row.get("name") or kind_label(kind)),
        "app_name": str(row.get("app_name") or ""),
        "has_app_key": bool(row.get("app_key")),
        "has_secret": bool(row.get("secret_key")),
        "authorized": authorized,
        "user_label": str(row.get("user_label") or ""),
        "ready": ready and authorized,
        "message": message,
    }


def save_raw(row: dict[str, Any]) -> dict[str, Any]:
    items = list_raw()
    found = False
    for index, item in enumerate(items):
        if str(item.get("id")) == str(row.get("id")):
            items[index] = row
            found = True
            break
    if not found:
        items.append(row)
    bundle = _bundle()
    bundle["accounts"] = items
    _save_bundle(bundle)
    return row


def delete_raw(account_id: str) -> bool:
    items = list_raw()
    next_items = [item for item in items if str(item.get("id")) != account_id]
    if len(next_items) == len(items):
        return False
    bundle = _bundle()
    bundle["accounts"] = next_items
    _save_bundle(bundle)
    return True


def new_id() -> str:
    return uuid.uuid4().hex[:12]
