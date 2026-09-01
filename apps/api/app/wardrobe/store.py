"""衣橱图片存在本机 data/wardrobe。"""

from pathlib import Path

from app.core.config import get_settings

ALLOWED_FILES = {"original.png", "cutout.png", "modeled.png", "look.png", "model-reference.png"}


def wardrobe_root() -> Path:
    root = get_settings().repo_root / "data" / "wardrobe"
    root.mkdir(parents=True, exist_ok=True)
    return root


def item_dir(item_id: int) -> Path:
    path = wardrobe_root() / "items" / str(item_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def look_dir(look_id: int) -> Path:
    path = wardrobe_root() / "looks" / str(look_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def tmp_dir() -> Path:
    path = wardrobe_root() / "tmp"
    path.mkdir(parents=True, exist_ok=True)
    return path


def reference_path() -> Path:
    return wardrobe_root() / "model-reference.png"


def style_dir(style_id: int) -> Path:
    path = wardrobe_root() / "styles" / str(style_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def list_style_files(style_id: int) -> list[Path]:
    return sorted(p for p in style_dir(style_id).glob("*.png") if p.stem.isdigit())


def read_style_file(style_id: int, name: str) -> Path | None:
    if not name.endswith(".png") or not name[:-4].isdigit():
        return None
    path = style_dir(style_id) / name
    return path if path.is_file() else None


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def read_item_file(item_id: int, name: str) -> Path | None:
    if name not in ALLOWED_FILES:
        return None
    path = item_dir(item_id) / name
    return path if path.is_file() else None
