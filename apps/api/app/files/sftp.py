"""文件柜远程盘：用账号密码连服务器上的一个文件夹。"""

from __future__ import annotations

import os
import posixpath
import stat
import subprocess
import tempfile
import threading
from datetime import datetime
from pathlib import Path

import paramiko

from app.core.config import get_settings
from app.core.local_settings import load_local_settings
from app.files.store import crumbs, preview_kind

_lock = threading.Lock()
_cached: tuple[tuple, paramiko.SSHClient, paramiko.SFTPClient] | None = None


def sftp_config() -> dict:
    stored = load_local_settings(get_settings().repo_root).get("files") or {}
    if not isinstance(stored, dict):
        return {}
    raw = stored.get("sftp") if isinstance(stored.get("sftp"), dict) else {}
    return {
        "host": str(raw.get("host") or "").strip(),
        "port": int(raw.get("port") or 22),
        "user": str(raw.get("user") or "").strip(),
        "password": str(raw.get("password") or ""),
        "remote": str(raw.get("remote") or "").strip() or "/",
    }


def sftp_public() -> dict:
    cfg = sftp_config()
    configured = bool(cfg["host"] and cfg["user"] and cfg["password"] and cfg["remote"])
    return {
        "host": cfg["host"],
        "port": cfg["port"],
        "user": cfg["user"],
        "remote": cfg["remote"],
        "has_password": bool(cfg["password"]),
        "configured": configured,
        "ready": configured,
    }


def _close_cached() -> None:
    global _cached
    if _cached is None:
        return
    client, sftp = _cached[1], _cached[2]
    try:
        sftp.close()
    except OSError:
        pass
    try:
        client.close()
    except OSError:
        pass
    _cached = None


def reset_connection() -> None:
    with _lock:
        _close_cached()


def _connect(cfg: dict | None = None) -> paramiko.SFTPClient:
    global _cached
    cfg = cfg or sftp_config()
    if not (cfg["host"] and cfg["user"] and cfg["password"]):
        raise ValueError("请先去设置填服务器地址、账号和密码")
    key = (cfg["host"], cfg["port"], cfg["user"], cfg["password"], cfg["remote"])
    with _lock:
        if _cached and _cached[0] == key:
            try:
                _cached[2].stat(cfg["remote"] or ".")
                return _cached[2]
            except OSError:
                _close_cached()
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                cfg["host"],
                port=cfg["port"],
                username=cfg["user"],
                password=cfg["password"],
                timeout=15,
                allow_agent=False,
                look_for_keys=False,
            )
            sftp = client.open_sftp()
        except Exception as exc:
            try:
                client.close()
            except OSError:
                pass
            raise ValueError(f"连不上服务器：{exc}") from exc
        _cached = (key, client, sftp)
        return sftp


def test_connection(cfg: dict) -> None:
    """试连一次，确认文件夹在。"""

    sftp = _connect(cfg)
    root = posixpath.normpath(cfg["remote"] or "/")
    try:
        info = sftp.stat(root)
    except OSError as exc:
        raise ValueError(f"服务器上找不到这个文件夹：{exc}") from exc
    if not stat.S_ISDIR(info.st_mode or 0):
        raise ValueError("远程路径必须是文件夹")


def _root() -> str:
    cfg = sftp_config()
    if not cfg["host"] or not cfg["user"] or not cfg["password"]:
        raise ValueError("请先去设置填服务器")
    return posixpath.normpath(cfg["remote"] or "/")


def _parts(rel: str) -> list[str]:
    parts: list[str] = []
    for part in (rel or "").replace("\\", "/").strip("/").split("/"):
        if not part or part == ".":
            continue
        if part == ".." or "/" in part or "\\" in part:
            raise ValueError("路径不合法")
        parts.append(part)
    return parts


def resolve_inside(rel: str) -> str:
    root = _root()
    parts = _parts(rel)
    path = posixpath.normpath(posixpath.join(root, *parts) if parts else root)
    if path != root and not path.startswith(root.rstrip("/") + "/"):
        raise ValueError("不能访问根目录外面")
    return path


def rel_of(path: str, root: str) -> str:
    if posixpath.normpath(path) == posixpath.normpath(root):
        return ""
    return posixpath.relpath(path, root).replace("\\", "/")


def _exists(sftp: paramiko.SFTPClient, path: str) -> bool:
    try:
        sftp.stat(path)
        return True
    except OSError:
        return False


def unique_name(sftp: paramiko.SFTPClient, folder: str, name: str) -> str:
    name = Path(name).name.strip() or "未命名"
    if name in {".", ".."}:
        raise ValueError("名字不合法")
    candidate = name
    stem = Path(name).stem
    suffix = Path(name).suffix
    index = 1
    while _exists(sftp, posixpath.join(folder, candidate)):
        candidate = f"{stem}-{index}{suffix}"
        index += 1
    return candidate


def entry_dict(sftp: paramiko.SFTPClient, path: str, root: str, info: paramiko.SFTPAttributes | None = None) -> dict:
    info = info or sftp.stat(path)
    kind = "dir" if stat.S_ISDIR(info.st_mode or 0) else "file"
    mtime = datetime.fromtimestamp(info.st_mtime).isoformat(timespec="seconds") if info.st_mtime else ""
    return {
        "name": posixpath.basename(path) or path,
        "path": rel_of(path, root),
        "kind": kind,
        "size": 0 if kind == "dir" else int(info.st_size or 0),
        "mtime": mtime,
        "preview": preview_kind(posixpath.basename(path)) if kind == "file" else "",
    }


def list_entries(rel: str) -> dict:
    sftp = _connect()
    root = _root()
    folder = resolve_inside(rel)
    try:
        children = sftp.listdir_attr(folder)
    except OSError as exc:
        raise ValueError(f"打不开这个文件夹：{exc}") from exc
    items = []
    for child in children:
        path = posixpath.join(folder, child.filename)
        items.append(entry_dict(sftp, path, root, child))
    items.sort(key=lambda item: (item["kind"] != "dir", item["name"].lower()))
    current = rel_of(folder, root)
    cfg = sftp_config()
    return {
        "root": f"{cfg['user']}@{cfg['host']}:{root}",
        "path": current,
        "crumbs": crumbs(current),
        "items": items,
    }


def search_entries(query: str, rel: str = "") -> dict:
    sftp = _connect()
    root = _root()
    folder = resolve_inside(rel)
    needle = (query or "").strip().lower()
    current = rel_of(folder, root)
    if not needle:
        return {"query": "", "path": current, "items": []}
    found: list[dict] = []

    def walk(base: str) -> None:
        if len(found) >= 200:
            return
        try:
            children = sftp.listdir_attr(base)
        except OSError:
            return
        for child in children:
            path = posixpath.join(base, child.filename)
            if needle in child.filename.lower():
                found.append(entry_dict(sftp, path, root, child))
            if len(found) >= 200:
                return
            if stat.S_ISDIR(child.st_mode or 0):
                walk(path)

    walk(folder)
    found.sort(key=lambda item: (item["kind"] != "dir", item["path"].lower()))
    return {"query": query.strip(), "path": current, "items": found}


def make_dir(rel: str, name: str) -> dict:
    sftp = _connect()
    root = _root()
    folder = resolve_inside(rel)
    dest = posixpath.join(folder, unique_name(sftp, folder, name))
    sftp.mkdir(dest)
    return entry_dict(sftp, dest, root)


def save_upload(rel: str, filename: str, data: bytes) -> dict:
    sftp = _connect()
    root = _root()
    folder = resolve_inside(rel)
    dest = posixpath.join(folder, unique_name(sftp, folder, filename))
    with sftp.open(dest, "wb") as handle:
        handle.write(data)
    return entry_dict(sftp, dest, root)


def rename_entry(rel: str, name: str) -> dict:
    sftp = _connect()
    root = _root()
    path = resolve_inside(rel)
    if path == root:
        raise ValueError("不能改根目录的名字")
    dest = posixpath.join(posixpath.dirname(path), Path(name).name.strip())
    if posixpath.basename(dest) in {".", ".."} or not posixpath.basename(dest):
        raise ValueError("名字不合法")
    if dest == path:
        return entry_dict(sftp, path, root)
    if _exists(sftp, dest):
        raise ValueError("已有同名文件")
    sftp.rename(path, dest)
    return entry_dict(sftp, dest, root)


def move_entry(rel: str, dest_rel: str) -> dict:
    sftp = _connect()
    root = _root()
    path = resolve_inside(rel)
    if path == root:
        raise ValueError("不能移动根目录")
    folder = resolve_inside(dest_rel)
    info = sftp.stat(folder)
    if not stat.S_ISDIR(info.st_mode or 0):
        raise ValueError("目标必须是文件夹")
    if folder == path or folder.startswith(path.rstrip("/") + "/"):
        raise ValueError("不能移到自己里面")
    dest = posixpath.join(folder, unique_name(sftp, folder, posixpath.basename(path)))
    sftp.rename(path, dest)
    return entry_dict(sftp, dest, root)


def _rmtree(sftp: paramiko.SFTPClient, path: str) -> None:
    for child in sftp.listdir_attr(path):
        item = posixpath.join(path, child.filename)
        if stat.S_ISDIR(child.st_mode or 0):
            _rmtree(sftp, item)
        else:
            sftp.remove(item)
    sftp.rmdir(path)


def delete_entry(rel: str) -> None:
    sftp = _connect()
    root = _root()
    path = resolve_inside(rel)
    if path == root:
        raise ValueError("不能删除根目录")
    try:
        info = sftp.stat(path)
    except OSError as exc:
        raise ValueError("没有这个文件") from exc
    if stat.S_ISDIR(info.st_mode or 0):
        _rmtree(sftp, path)
    else:
        sftp.remove(path)


def read_bytes(rel: str, limit: int | None = None) -> tuple[str, bytes]:
    sftp = _connect()
    path = resolve_inside(rel)
    try:
        info = sftp.stat(path)
    except OSError as exc:
        raise ValueError("没有这个文件") from exc
    if stat.S_ISDIR(info.st_mode or 0):
        raise ValueError("没有这个文件")
    with sftp.open(path, "rb") as handle:
        data = handle.read(limit) if limit else handle.read()
    return posixpath.basename(path), data


def open_with_system(rel: str) -> None:
    """先下到临时文件，再用电脑默认程序打开。"""

    name, data = read_bytes(rel)
    suffix = Path(name).suffix
    handle = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, prefix="bruceware-")
    handle.write(data)
    handle.close()
    try:
        if os.name == "nt":
            os.startfile(handle.name)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", handle.name])
    except OSError as exc:
        raise ValueError(f"打不开：{exc}") from exc
