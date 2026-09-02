"""文件柜：只在用户指定的根目录里读写，不能跑到外面。"""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from app.core.config import get_settings
from app.core.local_settings import load_local_settings

TEXT_EXTS = {".txt", ".md", ".json", ".csv", ".log", ".yaml", ".yml", ".ini"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
PDF_EXTS = {".pdf"}


def normalize_source(source: str) -> str:
    text = (source or "local").strip().lower()
    return "sftp" if text in {"sftp", "remote", "server"} else "local"


def sources_status() -> list[dict]:
    from app.files import sftp

    root, err = root_ready()
    local = {
        "id": "local",
        "label": "本地",
        "configured": bool(configured_root()),
        "ready": root is not None,
        "root": str(root) if root is not None else configured_root(),
        "message": err,
    }
    remote = sftp.sftp_public()
    label = f"{remote['user']}@{remote['host']}:{remote['remote']}" if remote["configured"] else ""
    return [
        local,
        {
            "id": "sftp",
            "label": "服务器",
            "configured": remote["configured"],
            "ready": remote["ready"],
            "root": label,
            "message": "" if remote["configured"] else "请先去设置填服务器",
        },
    ]


def configured_root() -> str:
    stored = load_local_settings(get_settings().repo_root).get("files") or {}
    if not isinstance(stored, dict):
        return ""
    return str(stored.get("root") or "").strip()


def root_ready() -> tuple[Path | None, str]:
    """没指定或文件夹不在，就不能用。"""

    raw = configured_root()
    if not raw:
        return None, "请先去设置指定文件根目录"
    path = Path(raw).expanduser()
    if not path.exists():
        return None, "根目录不存在，请在设置里改路径"
    if not path.is_dir():
        return None, "根目录必须是文件夹"
    return path.resolve(), ""


def resolve_inside(rel: str) -> Path:
    root, err = root_ready()
    if root is None:
        raise ValueError(err)
    rel = (rel or "").replace("\\", "/").strip("/")
    parts: list[str] = []
    for part in rel.split("/"):
        if not part or part == ".":
            continue
        if part == ".." or "/" in part or "\\" in part or part.endswith(":"):
            raise ValueError("路径不合法")
        parts.append(part)
    path = (root.joinpath(*parts) if parts else root).resolve()
    if path != root and root not in path.parents:
        raise ValueError("不能访问根目录外面")
    return path


def rel_of(path: Path, root: Path) -> str:
    if path == root:
        return ""
    return path.relative_to(root).as_posix()


def crumbs(rel: str) -> list[dict[str, str]]:
    items = [{"name": "根目录", "path": ""}]
    parts = [part for part in (rel or "").replace("\\", "/").split("/") if part]
    walked: list[str] = []
    for part in parts:
        walked.append(part)
        items.append({"name": part, "path": "/".join(walked)})
    return items


def unique_name(folder: Path, name: str) -> str:
    name = Path(name).name.strip() or "未命名"
    if name in {".", ".."}:
        raise ValueError("名字不合法")
    candidate = name
    stem = Path(name).stem
    suffix = Path(name).suffix
    index = 1
    while (folder / candidate).exists():
        candidate = f"{stem}-{index}{suffix}"
        index += 1
    return candidate


def preview_kind(name: str) -> str:
    ext = Path(name).suffix.lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in PDF_EXTS:
        return "pdf"
    if ext in TEXT_EXTS:
        return "text"
    return ""


def entry_dict(path: Path, root: Path) -> dict:
    stat = path.stat()
    kind = "dir" if path.is_dir() else "file"
    return {
        "name": path.name,
        "path": rel_of(path, root),
        "kind": kind,
        "size": 0 if kind == "dir" else stat.st_size,
        "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        "preview": preview_kind(path.name) if kind == "file" else "",
    }


def list_entries(rel: str, source: str = "local") -> dict:
    if normalize_source(source) == "sftp":
        from app.files import sftp

        return sftp.list_entries(rel)
    root, err = root_ready()
    if root is None:
        raise ValueError(err)
    folder = resolve_inside(rel)
    if not folder.is_dir():
        raise ValueError("这不是文件夹")
    items = [entry_dict(child, root) for child in folder.iterdir() if child.exists()]
    items.sort(key=lambda item: (item["kind"] != "dir", item["name"].lower()))
    current = rel_of(folder, root)
    return {
        "root": str(root),
        "path": current,
        "crumbs": crumbs(current),
        "items": items,
    }


def search_entries(query: str, rel: str = "", source: str = "local") -> dict:
    if normalize_source(source) == "sftp":
        from app.files import sftp

        return sftp.search_entries(query, rel)
    root, err = root_ready()
    if root is None:
        raise ValueError(err)
    folder = resolve_inside(rel)
    if not folder.is_dir():
        raise ValueError("这不是文件夹")
    needle = (query or "").strip().lower()
    if not needle:
        return {"query": "", "path": rel_of(folder, root), "items": []}
    found: list[dict] = []
    for child in folder.rglob("*"):
        if needle in child.name.lower():
            found.append(entry_dict(child, root))
        if len(found) >= 200:
            break
    found.sort(key=lambda item: (item["kind"] != "dir", item["path"].lower()))
    return {"query": query.strip(), "path": rel_of(folder, root), "items": found}


def make_dir(rel: str, name: str, source: str = "local") -> dict:
    if normalize_source(source) == "sftp":
        from app.files import sftp

        return sftp.make_dir(rel, name)
    folder = resolve_inside(rel)
    if not folder.is_dir():
        raise ValueError("这不是文件夹")
    dest = folder / unique_name(folder, name)
    dest.mkdir()
    root, _ = root_ready()
    assert root is not None
    return entry_dict(dest, root)


def save_upload(rel: str, filename: str, data: bytes, source: str = "local") -> dict:
    if normalize_source(source) == "sftp":
        from app.files import sftp

        return sftp.save_upload(rel, filename, data)
    folder = resolve_inside(rel)
    if not folder.is_dir():
        raise ValueError("这不是文件夹")
    dest = folder / unique_name(folder, filename)
    dest.write_bytes(data)
    root, _ = root_ready()
    assert root is not None
    return entry_dict(dest, root)


def rename_entry(rel: str, name: str, source: str = "local") -> dict:
    if normalize_source(source) == "sftp":
        from app.files import sftp

        return sftp.rename_entry(rel, name)
    path = resolve_inside(rel)
    root, err = root_ready()
    if root is None:
        raise ValueError(err)
    if path == root:
        raise ValueError("不能改根目录的名字")
    dest = path.parent / Path(name).name.strip()
    if dest.name in {".", ".."} or not dest.name:
        raise ValueError("名字不合法")
    if dest == path:
        return entry_dict(path, root)
    if dest.exists():
        raise ValueError("已有同名文件")
    path.rename(dest)
    return entry_dict(dest, root)


def move_entry(rel: str, dest_rel: str, source: str = "local") -> dict:
    if normalize_source(source) == "sftp":
        from app.files import sftp

        return sftp.move_entry(rel, dest_rel)
    path = resolve_inside(rel)
    root, err = root_ready()
    if root is None:
        raise ValueError(err)
    if path == root:
        raise ValueError("不能移动根目录")
    folder = resolve_inside(dest_rel)
    if not folder.is_dir():
        raise ValueError("目标必须是文件夹")
    if folder == path or (path.is_dir() and (folder == path or path in folder.parents)):
        raise ValueError("不能移到自己里面")
    dest = folder / unique_name(folder, path.name)
    shutil.move(str(path), str(dest))
    return entry_dict(dest, root)


def delete_entry(rel: str, source: str = "local") -> None:
    if normalize_source(source) == "sftp":
        from app.files import sftp

        sftp.delete_entry(rel)
        return
    path = resolve_inside(rel)
    root, err = root_ready()
    if root is None:
        raise ValueError(err)
    if path == root:
        raise ValueError("不能删除根目录")
    if path.is_dir():
        shutil.rmtree(path)
    elif path.is_file():
        path.unlink()
    else:
        raise ValueError("没有这个文件")


def read_bytes(rel: str, source: str = "local", limit: int | None = None) -> tuple[str, bytes]:
    if normalize_source(source) == "sftp":
        from app.files import sftp

        return sftp.read_bytes(rel, limit)
    path = resolve_inside(rel)
    if not path.is_file():
        raise ValueError("没有这个文件")
    with path.open("rb") as handle:
        data = handle.read(limit) if limit else handle.read()
    return path.name, data


def open_with_system(rel: str, source: str = "local") -> None:
    """用电脑默认程序打开，像资源管理器双击。"""

    if normalize_source(source) == "sftp":
        from app.files import sftp

        sftp.open_with_system(rel)
        return
    path = resolve_inside(rel)
    if not path.exists():
        raise ValueError("没有这个文件")
    try:
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except OSError as exc:
        raise ValueError(f"打不开：{exc}") from exc
