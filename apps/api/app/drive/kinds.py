"""已接和预留的网盘种类。以后加盘只在这里登记。"""

KINDS = {
    "baidu": {"label": "百度网盘", "ready": True},
    "aliyun": {"label": "阿里云盘", "ready": False},
    "webdav": {"label": "WebDAV", "ready": False},
}


def list_kinds() -> list[dict]:
    return [{"id": key, **value} for key, value in KINDS.items()]


def kind_label(kind: str) -> str:
    item = KINDS.get(kind) or {}
    return str(item.get("label") or kind)


def kind_ready(kind: str) -> bool:
    item = KINDS.get(kind) or {}
    return bool(item.get("ready"))
