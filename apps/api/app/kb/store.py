"""知识库磁盘：相对路径、哈希、安全文件名。"""

from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path

from app.core.generated import app_data_dir
from app.files.store import preview_kind


def kb_dir() -> Path:
    """知识库根目录，和衣橱一样跟着 app_data_dir。"""

    folder = app_data_dir() / "kb"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def library_dir(library_id: int) -> Path:
    folder = kb_dir() / str(library_id)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def safe_filename(name: str) -> str:
    text = Path(name or "").name.strip() or "未命名"
    text = re.sub(r'[\\/:*?"<>|]', "_", text)
    return text[:180]


def file_digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def kind_of(name: str) -> str:
    preview = preview_kind(name)
    return preview or "other"


def parse_status_of(kind: str) -> str:
    return "ready" if kind in {"pdf", "image", "text"} else "no_text"


def abs_path(library_id: int, rel_path: str) -> Path:
    rel = (rel_path or "").replace("\\", "/").lstrip("/")
    root = library_dir(library_id).resolve()
    target = (root / rel).resolve()
    target.relative_to(root)
    return target


def write_bytes(library_id: int, rel_path: str, data: bytes) -> None:
    path = abs_path(library_id, rel_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def remove_file(library_id: int, rel_path: str) -> None:
    if not rel_path:
        return
    try:
        path = abs_path(library_id, rel_path)
    except ValueError:
        return
    if path.is_file():
        path.unlink()


def remove_library_dir(library_id: int) -> None:
    folder = (kb_dir() / str(library_id)).resolve()
    root = kb_dir().resolve()
    try:
        folder.relative_to(root)
    except ValueError:
        return
    if folder.is_dir():
        shutil.rmtree(folder, ignore_errors=True)
