"""扫描 modules/ 下的 manifest.yaml，发现已安装模块。"""

from dataclasses import asdict, dataclass

import yaml

from app.core.config import get_settings
from app.core.local_settings import load_local_settings


@dataclass
class ModuleInfo:
    """模块名片，给侧栏和设置页用。"""

    id: str
    name: str
    description: str
    version: str
    path: str
    route: str
    kind: str
    enabled: bool
    pinned: bool


def flag_ids(key: str) -> set[str]:
    """读取本机设置里的模块名单，如 disabled / unpinned。"""

    return _id_set(get_settings().repo_root, key)


def _id_set(repo_root, key: str) -> set[str]:
    stored = load_local_settings(repo_root).get("modules") or {}
    raw = stored.get(key) if isinstance(stored, dict) else []
    if not isinstance(raw, list):
        return set()
    return {str(item) for item in raw}


def discover_modules() -> list[ModuleInfo]:
    """读取各模块文件夹里的说明文件。没有或读失败就跳过。"""

    settings = get_settings()
    root = settings.modules_dir
    if not root.is_dir():
        return []

    disabled = _id_set(settings.repo_root, "disabled")
    unpinned = _id_set(settings.repo_root, "unpinned")
    items: list[ModuleInfo] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        manifest_path = child / "manifest.yaml"
        if not manifest_path.is_file():
            continue
        try:
            raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        module_id = str(raw.get("id") or child.name).strip()
        if not module_id:
            continue
        web = raw.get("web") if isinstance(raw.get("web"), dict) else {}
        route = str(web.get("route_prefix") or f"/m/{module_id}")
        if not route.startswith("/m/"):
            route = f"/m/{module_id}"
        kind = str(raw.get("kind") or "app").strip()
        if kind not in ("common", "app"):
            kind = "app"
        items.append(
            ModuleInfo(
                id=module_id,
                name=str(raw.get("name") or web.get("nav_label") or module_id),
                description=str(raw.get("description") or ""),
                version=str(raw.get("version") or ""),
                path=str(child.relative_to(settings.repo_root)),
                route=route,
                kind=kind,
                enabled=True if kind == "common" else module_id not in disabled,
                pinned=True if kind == "common" else module_id not in unpinned,
            )
        )
    return items


def modules_as_dicts() -> list[dict]:
    return [asdict(item) for item in discover_modules()]
