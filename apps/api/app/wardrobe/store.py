"""衣橱图片存在本机 data/wardrobe。"""

from pathlib import Path

from app.core.config import get_settings

ALLOWED_FILES = {"original.png", "cutout.png", "modeled.png", "look.png", "model-reference.png"}


def _is_look_style_name(name: str) -> bool:
    """搭配目录里当时拍下来的风格图：style-1.png。"""

    return name.startswith("style-") and name.endswith(".png") and name[6:-4].isdigit()


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


def list_look_style_files(look_id: int) -> list[Path]:
    """这套搭配生成时保存下来的风格参考图。"""

    return sorted(p for p in look_dir(look_id).glob("style-*.png") if _is_look_style_name(p.name))


def look_style_name(look_id: int, title: str = "") -> str:
    """读搭配当时记下的风格名；没有文件就从标题里拆。"""

    path = look_dir(look_id) / "style-name.txt"
    if path.is_file():
        text = path.read_text(encoding="utf-8").strip()
        if text:
            return text
    if " · " in (title or ""):
        return title.rsplit(" · ", 1)[-1]
    return ""


def look_prompt(look_id: int) -> str:
    """读这套搭配生成时用的提示词。"""

    path = look_dir(look_id) / "prompt.txt"
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def save_look_prompt(look_id: int, prompt: str) -> None:
    if not prompt:
        return
    write_bytes(look_dir(look_id) / "prompt.txt", prompt.encode("utf-8"))


def save_look_style_name(look_id: int, name: str) -> None:
    if not name:
        return
    write_bytes(look_dir(look_id) / "style-name.txt", name.encode("utf-8"))


def copy_look_style(src_id: int, dst_id: int) -> None:
    """把一套搭配记下的风格图拷到新搭配，裂变时沿用原来的参考。"""

    name = look_style_name(src_id)
    if name:
        save_look_style_name(dst_id, name)
    for index, path in enumerate(list_look_style_files(src_id), start=1):
        write_bytes(look_dir(dst_id) / f"style-{index}.png", path.read_bytes())


def copy_style_into_look(look_id: int, style_id: int, style_name: str) -> None:
    """把当时的风格图复制进搭配目录，之后改风格不会动到旧搭配。"""

    save_look_style_name(look_id, style_name)
    for index, path in enumerate(list_style_files(style_id), start=1):
        write_bytes(look_dir(look_id) / f"style-{index}.png", path.read_bytes())


def read_look_file(look_id: int, name: str) -> Path | None:
    if name not in ("look.png", "source.png") and not _is_look_style_name(name):
        return None
    path = look_dir(look_id) / name
    return path if path.is_file() else None


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def read_item_file(item_id: int, name: str) -> Path | None:
    if name not in ALLOWED_FILES:
        return None
    path = item_dir(item_id) / name
    return path if path.is_file() else None
