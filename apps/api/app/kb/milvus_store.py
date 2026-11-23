"""可选 Milvus。没填地址就不用；失败只提示，提问退回本机逐条比。"""

from __future__ import annotations

import time
from contextvars import ContextVar
from typing import Any

from app.core.config import get_settings
from app.core.local_settings import load_local_settings

_DEFAULT_COLLECTION = "kb_chunks"
_NOTE_TTL = 5
_note: ContextVar[tuple[float, str]] = ContextVar("kb_milvus_note", default=(0.0, ""))
_client: Any = None
_client_key = ""
_down_until = 0.0


def load_milvus() -> dict[str, str]:
    """读本机设置。地址空着就是关闭。"""

    stored = load_local_settings(get_settings().repo_root).get("milvus") or {}
    if not isinstance(stored, dict):
        stored = {}
    collection = str(stored.get("collection") or "").strip() or _DEFAULT_COLLECTION
    return {
        "uri": str(stored.get("uri") or "").strip(),
        "token": str(stored.get("token") or "").strip(),
        "collection": _safe_name(collection),
    }


def milvus_public() -> dict[str, Any]:
    """给设置页看。口令不回显。"""

    cfg = load_milvus()
    return {
        "uri": cfg["uri"],
        "collection": cfg["collection"],
        "enabled": bool(cfg["uri"]),
        "has_token": bool(cfg["token"]),
    }


def reset_milvus_client() -> None:
    """改过地址或口令后丢掉旧连接。"""

    global _client, _client_key, _down_until
    _client = None
    _client_key = ""
    _down_until = 0.0


def take_milvus_note() -> str:
    """取走刚才的同步提示。过几秒就作废，避免串到下一次操作。"""

    ts, text = _note.get()
    _note.set((0.0, ""))
    if not text or time.time() - ts > _NOTE_TTL:
        return ""
    return text


def enabled() -> bool:
    return bool(load_milvus()["uri"])


def delete_document_vectors(document_id: int) -> None:
    """删一份资料在 Milvus 里的段。没开或失败都不抛错。"""

    if not enabled():
        return
    _run(lambda client, base: _delete_where(client, base, f"document_id == {int(document_id)}"))


def delete_library_vectors(library_id: int) -> None:
    """删一个库在 Milvus 里的段。"""

    if not enabled():
        return
    _run(lambda client, base: _delete_where(client, base, f"library_id == {int(library_id)}"))


def replace_document_vectors(
    library_id: int,
    document_id: int,
    profile: str,
    rows: list[tuple[int, list[float]]],
) -> None:
    """整份重写这一资料的向量。本机已经写好时才调用。"""

    if not enabled():
        return
    delete_document_vectors(document_id)
    if rows:
        upsert_vectors(library_id, document_id, profile, rows)


def upsert_vectors(
    library_id: int,
    document_id: int,
    profile: str,
    rows: list[tuple[int, list[float]]],
) -> None:
    """写入或盖住这几段。维度不同会落到另一个集合，避免和旧模型混用。"""

    if not enabled() or not rows:
        return

    def act(client: Any, base: str) -> None:
        dim = len(rows[0][1])
        if dim <= 0 or any(len(vec) != dim for _index, vec in rows):
            raise ValueError("向量维度不一致")
        name = f"{base}_{dim}"
        _ensure_collection(client, name, dim)
        data = [
            {
                "pk": f"{int(library_id)}_{int(document_id)}_{int(index)}",
                "vector": vec,
                "library_id": int(library_id),
                "document_id": int(document_id),
                "chunk_index": int(index),
                "profile": (profile or "")[:200],
            }
            for index, vec in rows
        ]
        client.upsert(collection_name=name, data=data)

    _run(act)


def search_hits(
    library_id: int,
    profile: str,
    vector: list[float],
    doc_ids: set[int] | None,
    expect: int = 0,
    limit: int = 40,
) -> list[tuple[int, int, float]] | None:
    """找到相近段。返回 None 表示没开、失败或还没同步齐，调用方改走本机逐条比。"""

    if not enabled() or not vector or _cooling():
        return None
    try:
        client, base = _connect()
        name = f"{base}_{len(vector)}"
        if not client.has_collection(name):
            return None
        expr, post = _search_filter(library_id, profile, doc_ids)
        remote_count = _count(client, name, expr if post is None else _library_filter(library_id, profile))
        if remote_count is None or remote_count < expect:
            return None
        found = client.search(
            collection_name=name,
            data=[vector],
            limit=limit,
            filter=expr,
            output_fields=["document_id", "chunk_index"],
            search_params={"metric_type": "COSINE"},
        )
    except Exception:
        return None
    hits = _read_hits(found)
    if post is not None:
        hits = [item for item in hits if item[0] in post]
        if not hits:
            return None
    return hits


def _library_filter(library_id: int, profile: str) -> str:
    return f"library_id == {int(library_id)} and profile == {_quote(profile)}"


def _count(client: Any, name: str, expr: str) -> int | None:
    rows = client.query(collection_name=name, filter=expr, output_fields=["count(*)"])
    if not rows or not isinstance(rows[0], dict):
        return 0
    for key, value in rows[0].items():
        if "count" in str(key):
            return int(value)
    return None


def _cooling() -> bool:
    return time.time() < _down_until


def _mark_down() -> None:
    global _down_until, _client, _client_key
    _down_until = time.time() + 60
    _client = None
    _client_key = ""


def _search_filter(library_id: int, profile: str, doc_ids: set[int] | None) -> tuple[str, set[int] | None]:
    expr = _library_filter(library_id, profile)
    if doc_ids is None:
        return expr, None
    ids = sorted(int(item) for item in doc_ids)
    if len(ids) <= 1500:
        return expr + " and document_id in [" + ",".join(str(item) for item in ids) + "]", None
    return expr, set(ids)


def _read_hits(found: Any) -> list[tuple[int, int, float]]:
    rows = found[0] if found else []
    hits: list[tuple[int, int, float]] = []
    for hit in rows:
        if not isinstance(hit, dict):
            continue
        entity = hit.get("entity") if isinstance(hit.get("entity"), dict) else hit
        try:
            document_id = int(entity.get("document_id"))
            chunk_index = int(entity.get("chunk_index"))
            score = float(hit.get("distance") if hit.get("distance") is not None else hit.get("score") or 0)
        except (TypeError, ValueError):
            continue
        hits.append((document_id, chunk_index, score))
    return hits


def _run(action) -> None:
    if _cooling():
        _remember(RuntimeError("暂时连不上"))
        return
    try:
        client, base = _connect()
        action(client, base)
    except Exception as exc:
        _mark_down()
        _remember(exc)


def _connect() -> tuple[Any, str]:
    global _client, _client_key
    cfg = load_milvus()
    if not cfg["uri"]:
        raise RuntimeError("没填 Milvus 地址")
    key = cfg["uri"] + "\n" + cfg["token"]
    if _client is None or _client_key != key:
        try:
            from pymilvus import MilvusClient
        except ImportError as exc:
            raise RuntimeError("没安装 Milvus 组件") from exc
        _client = MilvusClient(uri=cfg["uri"], token=cfg["token"] or "", timeout=3)
        _client_key = key
    return _client, cfg["collection"]


def _ensure_collection(client: Any, name: str, dim: int) -> None:
    if client.has_collection(name):
        return
    from pymilvus import DataType

    schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
    schema.add_field("pk", DataType.VARCHAR, is_primary=True, max_length=80)
    schema.add_field("vector", DataType.FLOAT_VECTOR, dim=dim)
    schema.add_field("library_id", DataType.INT64)
    schema.add_field("document_id", DataType.INT64)
    schema.add_field("chunk_index", DataType.INT64)
    schema.add_field("profile", DataType.VARCHAR, max_length=200)
    index_params = client.prepare_index_params()
    index_params.add_index(field_name="vector", index_type="AUTOINDEX", metric_type="COSINE")
    client.create_collection(collection_name=name, schema=schema, index_params=index_params)


def _delete_where(client: Any, base: str, expr: str) -> None:
    for name in _dim_collections(client, base):
        client.delete(collection_name=name, filter=expr)


def _dim_collections(client: Any, base: str) -> list[str]:
    prefix = base + "_"
    names: list[str] = []
    for name in client.list_collections():
        suffix = name[len(prefix) :] if name.startswith(prefix) else ""
        if suffix.isdigit():
            names.append(name)
    return names


def _safe_name(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name.strip())
    if not cleaned or cleaned[0].isdigit():
        cleaned = "kb_" + cleaned
    return cleaned[:40] or _DEFAULT_COLLECTION


def _quote(value: str) -> str:
    escaped = (value or "").replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped[:200]}"'


def _remember(exc: BaseException) -> None:
    text = str(exc).replace("\n", " ").strip()[:120] or "Milvus 不可用"
    _note.set((time.time(), f"Milvus 没同步上，本机向量已保存：{text}"))
