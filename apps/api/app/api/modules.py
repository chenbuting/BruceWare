"""已发现的模块列表，以及功能模块开关。"""

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.local_settings import load_local_settings, save_local_settings
from app.core.response import fail, ok
from app.modules.registry import discover_modules, flag_ids, modules_as_dicts

router = APIRouter()


class ModuleEnabledBody(BaseModel):
    enabled: bool


class ModulePinnedBody(BaseModel):
    pinned: bool


def _save_id_set(key: str, values: set[str]) -> list[dict]:
    settings = get_settings()
    data = load_local_settings(settings.repo_root)
    modules = data.get("modules") if isinstance(data.get("modules"), dict) else {}
    modules[key] = sorted(values)
    data["modules"] = modules
    save_local_settings(settings.repo_root, data)
    return modules_as_dicts()


@router.get("/modules")
def list_modules():
    """扫描 modules/，带上类型和开关状态。"""

    items = modules_as_dicts()
    return ok({"items": items, "count": len(items)})


@router.put("/modules/{module_id}/enabled")
def set_module_enabled(module_id: str, body: ModuleEnabledBody):
    """只允许开关功能模块。公共模块不能关。"""

    found = next((item for item in discover_modules() if item.id == module_id), None)
    if found is None:
        return fail("没有这个模块")
    if found.kind == "common":
        return fail("公共模块不能关闭")

    disabled = flag_ids("disabled")
    if body.enabled:
        disabled.discard(module_id)
    else:
        disabled.add(module_id)
    items = _save_id_set("disabled", disabled)
    return ok({"items": items, "count": len(items)})


@router.put("/modules/{module_id}/pinned")
def set_module_pinned(module_id: str, body: ModulePinnedBody):
    """只允许固定/取消固定功能模块。公共模块始终在侧栏。"""

    found = next((item for item in discover_modules() if item.id == module_id), None)
    if found is None:
        return fail("没有这个模块")
    if found.kind == "common":
        return fail("公共模块不能取消固定")

    unpinned = flag_ids("unpinned")
    if body.pinned:
        unpinned.discard(module_id)
    else:
        unpinned.add(module_id)
    items = _save_id_set("unpinned", unpinned)
    return ok({"items": items, "count": len(items)})
