"""项目数据：选了跟着走之后，放到文件根目录下的 BruceWare。"""

from __future__ import annotations

import shutil
from pathlib import Path

from app.core.config import get_settings
from app.core.local_settings import load_local_settings

SQLITE_NAMES = ("bruceware.db", "bruceware.db-wal", "bruceware.db-shm")


def files_stored() -> dict:
    stored = load_local_settings(get_settings().repo_root).get("files") or {}
    return stored if isinstance(stored, dict) else {}


def files_root_text() -> str:
    return str(files_stored().get("root") or "").strip()


def generated_follow() -> bool:
    return bool(files_stored().get("generated_follow"))


def app_data_dir_for(files_root: str, follow: bool) -> Path:
    raw = (files_root or "").strip()
    if follow and raw:
        path = Path(raw).expanduser()
        if path.is_dir():
            return path / "BruceWare"
    return get_settings().repo_root / "data"


def app_data_dir() -> Path:
    return app_data_dir_for(files_root_text(), generated_follow())


def wardrobe_dir_for(files_root: str, follow: bool) -> Path:
    return app_data_dir_for(files_root, follow) / "wardrobe"


def wardrobe_dir() -> Path:
    return wardrobe_dir_for(files_root_text(), generated_follow())


def sqlite_path_for(files_root: str, follow: bool) -> Path:
    return app_data_dir_for(files_root, follow) / "bruceware.db"


def sqlite_current_path(stored: dict) -> Path:
    """当前本地库文件位置。"""

    db = stored.get("database") if isinstance(stored.get("database"), dict) else {}
    text = str(db.get("sqlite_path") or "").strip()
    if not text:
        url = str(db.get("url") or "")
        if url.startswith("sqlite:///"):
            text = url[len("sqlite:///") :]
    if not text:
        return get_settings().repo_root / "data" / "bruceware.db"
    path = Path(text)
    if not path.is_absolute():
        path = get_settings().repo_root / path
    return path


def sqlite_outside_pack(files_root: str) -> bool:
    """本地库还没进根目录下的 BruceWare。"""

    stored = load_local_settings(get_settings().repo_root)
    if not uses_local_sqlite(stored):
        return False
    raw = (files_root or "").strip()
    if not raw:
        return False
    current = sqlite_current_path(stored)
    target = sqlite_path_for(raw, True)
    try:
        if current.resolve() == target.resolve():
            return False
    except OSError:
        pass
    return current.is_file() and current.stat().st_size > 0


def has_generated_files(folder: Path) -> bool:
    if not folder.is_dir():
        return False
    return any(item.is_file() for item in folder.rglob("*"))


def has_app_data(files_root: str, follow: bool) -> bool:
    pack = app_data_dir_for(files_root, follow)
    if has_generated_files(pack / "wardrobe"):
        return True
    db = pack / "bruceware.db"
    return db.is_file() and db.stat().st_size > 0


def generated_info() -> dict:
    pack = app_data_dir()
    leftover_db = sqlite_outside_pack(files_root_text())
    old_data = has_app_data(files_root_text(), generated_follow())
    return {
        "path": str(pack),
        "has_files": old_data or leftover_db,
        "follow": generated_follow(),
        "needs_move": (not generated_follow() and has_app_data(files_root_text(), False)) or leftover_db,
    }


def _nested(a: Path, b: Path) -> bool:
    try:
        a.resolve().relative_to(b.resolve())
        return True
    except (OSError, ValueError):
        return False


def _move_tree(src: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for child in list(src.iterdir()):
        target = dest / child.name
        if child.is_dir():
            _move_tree(child, target)
            try:
                child.rmdir()
            except OSError:
                pass
        elif not target.exists():
            shutil.move(str(child), str(target))


def _move_sqlite(old_dir: Path, new_pack: Path) -> None:
    new_pack.mkdir(parents=True, exist_ok=True)
    for name in SQLITE_NAMES:
        src = old_dir / name
        dest = new_pack / name
        if src.is_file() and not dest.exists():
            shutil.move(str(src), str(dest))


def move_app_data(old_files_root: str, new_files_root: str) -> None:
    """把衣橱图和本地库从旧位置挪到新根目录的 BruceWare。"""

    old_pack = app_data_dir_for(old_files_root, generated_follow())
    new_pack = app_data_dir_for(new_files_root, True)
    old_wardrobe = old_pack / "wardrobe"
    new_wardrobe = new_pack / "wardrobe"
    same = False
    try:
        same = old_pack.resolve() == new_pack.resolve()
    except OSError:
        pass
    if not same:
        if _nested(old_pack, new_pack) or _nested(new_pack, old_pack):
            raise ValueError("新旧目录套在一起，不能自动搬，请手动拷贝")
        if has_generated_files(old_wardrobe):
            new_wardrobe.mkdir(parents=True, exist_ok=True)
            _move_tree(old_wardrobe, new_wardrobe)
        _move_sqlite(old_pack, new_pack)
    stored = load_local_settings(get_settings().repo_root)
    current_db = sqlite_current_path(stored)
    try:
        already = current_db.resolve() == (new_pack / "bruceware.db").resolve()
    except OSError:
        already = False
    if current_db.is_file() and not already:
        _move_sqlite(current_db.parent, new_pack)


def move_wardrobe(old_files_root: str, new_files_root: str) -> None:
    move_app_data(old_files_root, new_files_root)


def uses_local_sqlite(stored: dict) -> bool:
    db = stored.get("database") if isinstance(stored.get("database"), dict) else {}
    mode = str(db.get("mode") or "")
    url = str(db.get("url") or "")
    return mode == "local" or url.startswith("sqlite") or not mode
