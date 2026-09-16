"""网盘路径：只允许正向目录，不能跳出。"""

from datetime import datetime
from pathlib import Path


TEXT_EXTS = {".txt", ".md", ".json", ".csv", ".log", ".yaml", ".yml", ".ini"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
PDF_EXTS = {".pdf"}


def normalize_path(raw: str) -> str:
    parts: list[str] = []
    for part in (raw or "").replace("\\", "/").split("/"):
        if not part or part == ".":
            continue
        if part == "..":
            raise ValueError("路径不合法")
        parts.append(part)
    return "/" + "/".join(parts) if parts else "/"


def join_path(folder: str, name: str) -> str:
    name = Path(name).name.strip()
    if not name or name in {".", ".."}:
        raise ValueError("名字不合法")
    folder = normalize_path(folder)
    return folder.rstrip("/") + "/" + name


def crumbs(path: str) -> list[dict[str, str]]:
    items = [{"name": "根目录", "path": "/"}]
    walked: list[str] = []
    for part in [item for item in normalize_path(path).split("/") if item]:
        walked.append(part)
        items.append({"name": part, "path": "/" + "/".join(walked)})
    return items


def preview_kind(name: str) -> str:
    ext = Path(name).suffix.lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in PDF_EXTS:
        return "pdf"
    if ext in TEXT_EXTS:
        return "text"
    return ""


def entry_of(name: str, path: str, is_dir: bool, size: int = 0, mtime: int = 0, fsid: int = 0) -> dict:
    kind = "dir" if is_dir else "file"
    stamp = datetime.fromtimestamp(mtime).isoformat(timespec="seconds") if mtime else ""
    return {
        "name": name,
        "path": normalize_path(path),
        "kind": kind,
        "size": 0 if is_dir else int(size or 0),
        "mtime": stamp,
        "preview": preview_kind(name) if kind == "file" else "",
        "fsid": int(fsid or 0),
    }
