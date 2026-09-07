"""知识库跟设置备份一起走：库记录、对话、原文和抽出的图。"""

from __future__ import annotations

import shutil
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.kb.models import KbAsset, KbChunk, KbDocument, KbFolder, KbLibrary, KbSession, KbSessionTurn
from app.kb.store import kb_dir, remove_library_dir, write_bytes


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value else ""


def _dt(raw: Any) -> datetime:
    text_value = str(raw or "").strip()
    if not text_value:
        return datetime.utcnow()
    try:
        return datetime.fromisoformat(text_value.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return datetime.utcnow()


def _as_list(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _int(raw: Any, default: int = 0) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _opt_int(raw: Any) -> int | None:
    if raw in (None, ""):
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def dump_kb(db: Session) -> dict[str, list[dict[str, Any]]]:
    """导出知识库表。文件另外打进 zip。"""

    libraries = db.scalars(select(KbLibrary).order_by(KbLibrary.id.asc())).all()
    folders = db.scalars(select(KbFolder).order_by(KbFolder.id.asc())).all()
    docs = db.scalars(select(KbDocument).order_by(KbDocument.id.asc())).all()
    chunks = db.scalars(select(KbChunk).order_by(KbChunk.id.asc())).all()
    assets = db.scalars(select(KbAsset).order_by(KbAsset.id.asc())).all()
    sessions = db.scalars(select(KbSession).order_by(KbSession.id.asc())).all()
    turns = db.scalars(select(KbSessionTurn).order_by(KbSessionTurn.id.asc())).all()
    return {
        "kb_libraries": [
            {
                "id": row.id,
                "name": row.name or "",
                "description": row.description or "",
                "policy_json": row.policy_json or "",
                "extra": row.extra or "",
                "created_at": _iso(row.created_at),
            }
            for row in libraries
        ],
        "kb_folders": [
            {
                "id": row.id,
                "library_id": row.library_id,
                "parent_id": row.parent_id,
                "name": row.name or "",
            }
            for row in folders
        ],
        "kb_documents": [
            {
                "id": row.id,
                "library_id": row.library_id,
                "folder_id": row.folder_id,
                "title": row.title or "",
                "file_name": row.file_name or "",
                "rel_path": row.rel_path or "",
                "source": row.source or "upload",
                "tags": row.tags or "",
                "file_hash": row.file_hash or "",
                "parse_status": row.parse_status or "ready",
                "kind": row.kind or "other",
                "evidence_level": row.evidence_level or "须出处",
                "files_ref": row.files_ref or "",
                "wiki_json": row.wiki_json or "",
                "embedding_profile": row.embedding_profile or "",
                "extra": row.extra or "",
                "search_text": row.search_text or "",
                "created_at": _iso(row.created_at),
                "updated_at": _iso(row.updated_at),
            }
            for row in docs
        ],
        "kb_chunks": [
            {
                "id": row.id,
                "library_id": row.library_id,
                "document_id": row.document_id,
                "chunk_index": row.chunk_index or 0,
                "text": row.text or "",
                "embedding": row.embedding or "",
                "profile": row.profile or "",
                "edited": int(row.edited or 0),
            }
            for row in chunks
        ],
        "kb_assets": [
            {
                "id": row.id,
                "library_id": row.library_id,
                "document_id": row.document_id,
                "rel_path": row.rel_path or "",
                "page": row.page or 0,
                "sort_order": row.sort_order or 0,
                "alt_text": row.alt_text or "",
                "ocr_text": row.ocr_text or "",
            }
            for row in assets
        ],
        "kb_sessions": [
            {
                "id": row.id,
                "library_id": row.library_id,
                "title": row.title or "新对话",
                "created_at": _iso(row.created_at),
                "updated_at": _iso(row.updated_at),
            }
            for row in sessions
        ],
        "kb_session_turns": [
            {
                "id": row.id,
                "session_id": row.session_id,
                "question": row.question or "",
                "answer": row.answer or "",
                "result_json": row.result_json or "",
                "created_at": _iso(row.created_at),
            }
            for row in turns
        ],
    }


def kb_file_entries(db: Session) -> list[tuple[int, str]]:
    """资料和抽出图的相对路径，去重。"""

    seen: set[tuple[int, str]] = set()
    items: list[tuple[int, str]] = []
    docs = db.scalars(select(KbDocument)).all()
    assets = db.scalars(select(KbAsset)).all()
    for row in (*docs, *assets):
        rel = (row.rel_path or "").replace("\\", "/").lstrip("/")
        if not rel:
            continue
        key = (int(row.library_id), rel)
        if key in seen:
            continue
        seen.add(key)
        items.append(key)
    return items


def payload_has_kb(payload: dict[str, Any]) -> bool:
    """新备份带知识库；旧 json 没有这些键，不要清掉现有库。"""

    try:
        version = int(payload.get("version") or 0)
    except (TypeError, ValueError):
        version = 0
    return version >= 2 or "kb_libraries" in payload


def clear_kb(db: Session) -> None:
    db.execute(delete(KbSessionTurn))
    db.execute(delete(KbSession))
    db.execute(delete(KbAsset))
    db.execute(delete(KbChunk))
    db.execute(delete(KbDocument))
    db.execute(delete(KbFolder))
    db.execute(delete(KbLibrary))


def wipe_kb_files(keep: set[int] | None = None) -> None:
    """删掉磁盘上的库目录。keep 里的先留着，由调用方再覆盖。"""

    root = kb_dir()
    for child in root.iterdir():
        if not child.is_dir() or not child.name.isdigit():
            continue
        lib_id = int(child.name)
        if keep is not None and lib_id in keep:
            continue
        shutil.rmtree(child, ignore_errors=True)


def restore_kb_files(blobs: dict[tuple[int, str], bytes], lib_map: dict[int, int] | None = None) -> None:
    """把 zip 里的文件写回对应库目录。"""

    written: set[int] = set()
    for old_lib, rel in blobs:
        if lib_map is None:
            new_lib = old_lib
        elif old_lib not in lib_map:
            continue
        else:
            new_lib = lib_map[old_lib]
        if new_lib not in written:
            remove_library_dir(new_lib)
            written.add(new_lib)
        try:
            write_bytes(new_lib, rel, blobs[(old_lib, rel)])
        except (ValueError, OSError):
            continue


def insert_kb_replace(db: Session, payload: dict[str, Any]) -> dict[str, int]:
    libraries = _as_list(payload.get("kb_libraries"))
    folders = _as_list(payload.get("kb_folders"))
    docs = _as_list(payload.get("kb_documents"))
    chunks = _as_list(payload.get("kb_chunks"))
    assets = _as_list(payload.get("kb_assets"))
    sessions = _as_list(payload.get("kb_sessions"))
    turns = _as_list(payload.get("kb_session_turns"))
    clear_kb(db)
    for item in libraries:
        fields = _library_fields(item)
        if item.get("id"):
            fields["id"] = _int(item["id"])
        db.add(KbLibrary(**fields))
    for item in folders:
        fields = _folder_fields(item)
        if item.get("id"):
            fields["id"] = _int(item["id"])
        db.add(KbFolder(**fields))
    for item in docs:
        fields = _document_fields(item)
        if item.get("id"):
            fields["id"] = _int(item["id"])
        db.add(KbDocument(**fields))
    for item in chunks:
        fields = _chunk_fields(item)
        if item.get("id"):
            fields["id"] = _int(item["id"])
        db.add(KbChunk(**fields))
    for item in assets:
        fields = _asset_fields(item)
        if item.get("id"):
            fields["id"] = _int(item["id"])
        db.add(KbAsset(**fields))
    for item in sessions:
        fields = _session_fields(item)
        if item.get("id"):
            fields["id"] = _int(item["id"])
        db.add(KbSession(**fields))
    for item in turns:
        fields = _turn_fields(item)
        if item.get("id"):
            fields["id"] = _int(item["id"])
        db.add(KbSessionTurn(**fields))
    db.flush()
    return {"kb_library": len(libraries), "kb_document": len(docs)}


def insert_kb_merge(db: Session, payload: dict[str, Any]) -> tuple[dict[str, int], dict[int, int]]:
    """合并进现有库，ID 重映射。返回计数和旧库 ID → 新库 ID。"""

    libraries = _as_list(payload.get("kb_libraries"))
    folders = _as_list(payload.get("kb_folders"))
    docs = _as_list(payload.get("kb_documents"))
    chunks = _as_list(payload.get("kb_chunks"))
    assets = _as_list(payload.get("kb_assets"))
    sessions = _as_list(payload.get("kb_sessions"))
    turns = _as_list(payload.get("kb_session_turns"))
    lib_map: dict[int, int] = {}
    folder_map: dict[int, int] = {}
    doc_map: dict[int, int] = {}
    session_map: dict[int, int] = {}
    for item in libraries:
        old_id = _int(item.get("id"))
        row = KbLibrary(**_library_fields(item))
        db.add(row)
        db.flush()
        if old_id:
            lib_map[old_id] = row.id
    for item in folders:
        old_id = _int(item.get("id"))
        old_lib = _int(item.get("library_id"))
        library_id = lib_map.get(old_lib)
        if library_id is None:
            continue
        row = KbFolder(library_id=library_id, parent_id=None, name=str(item.get("name") or "")[:200] or "未命名")
        db.add(row)
        db.flush()
        if old_id:
            folder_map[old_id] = row.id
    for item in folders:
        old_id = _int(item.get("id"))
        parent = _opt_int(item.get("parent_id"))
        if not old_id or parent is None:
            continue
        row = db.get(KbFolder, folder_map.get(old_id))
        new_parent = folder_map.get(parent)
        if row is not None and new_parent:
            row.parent_id = new_parent
    for item in docs:
        old_id = _int(item.get("id"))
        library_id = lib_map.get(_int(item.get("library_id")))
        if library_id is None:
            continue
        fields = _document_fields(item)
        fields["library_id"] = library_id
        old_folder = _opt_int(item.get("folder_id"))
        fields["folder_id"] = folder_map.get(old_folder) if old_folder else None
        row = KbDocument(**fields)
        db.add(row)
        db.flush()
        if old_id:
            doc_map[old_id] = row.id
    for item in chunks:
        library_id = lib_map.get(_int(item.get("library_id")))
        document_id = doc_map.get(_int(item.get("document_id")))
        if library_id is None or document_id is None:
            continue
        fields = _chunk_fields(item)
        fields["library_id"] = library_id
        fields["document_id"] = document_id
        db.add(KbChunk(**fields))
    for item in assets:
        library_id = lib_map.get(_int(item.get("library_id")))
        document_id = doc_map.get(_int(item.get("document_id")))
        if library_id is None or document_id is None:
            continue
        fields = _asset_fields(item)
        fields["library_id"] = library_id
        fields["document_id"] = document_id
        db.add(KbAsset(**fields))
    for item in sessions:
        old_id = _int(item.get("id"))
        library_id = lib_map.get(_int(item.get("library_id")))
        if library_id is None:
            continue
        fields = _session_fields(item)
        fields["library_id"] = library_id
        row = KbSession(**fields)
        db.add(row)
        db.flush()
        if old_id:
            session_map[old_id] = row.id
    for item in turns:
        session_id = session_map.get(_int(item.get("session_id")))
        if session_id is None:
            continue
        fields = _turn_fields(item)
        fields["session_id"] = session_id
        db.add(KbSessionTurn(**fields))
    db.flush()
    return {"kb_library": len(lib_map), "kb_document": len(doc_map)}, lib_map


def _library_fields(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": str(item.get("name") or "")[:120] or "未命名",
        "description": str(item.get("description") or "")[:500],
        "policy_json": str(item.get("policy_json") or ""),
        "extra": str(item.get("extra") or ""),
        "created_at": _dt(item.get("created_at")),
    }


def _folder_fields(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "library_id": _int(item.get("library_id")),
        "parent_id": _opt_int(item.get("parent_id")),
        "name": str(item.get("name") or "")[:200] or "未命名",
    }


def _document_fields(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "library_id": _int(item.get("library_id")),
        "folder_id": _opt_int(item.get("folder_id")),
        "title": str(item.get("title") or "")[:255],
        "file_name": str(item.get("file_name") or "")[:255],
        "rel_path": str(item.get("rel_path") or "")[:500],
        "source": str(item.get("source") or "upload")[:20],
        "tags": str(item.get("tags") or "")[:500],
        "file_hash": str(item.get("file_hash") or "")[:64],
        "parse_status": str(item.get("parse_status") or "ready")[:20],
        "kind": str(item.get("kind") or "other")[:20],
        "evidence_level": str(item.get("evidence_level") or "须出处")[:20],
        "files_ref": str(item.get("files_ref") or ""),
        "wiki_json": str(item.get("wiki_json") or ""),
        "embedding_profile": str(item.get("embedding_profile") or "")[:150],
        "extra": str(item.get("extra") or ""),
        "search_text": str(item.get("search_text") or ""),
        "created_at": _dt(item.get("created_at")),
        "updated_at": _dt(item.get("updated_at")),
    }


def _chunk_fields(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "library_id": _int(item.get("library_id")),
        "document_id": _int(item.get("document_id")),
        "chunk_index": _int(item.get("chunk_index")),
        "text": str(item.get("text") or ""),
        "embedding": str(item.get("embedding") or ""),
        "profile": str(item.get("profile") or "")[:150],
        "edited": 1 if _int(item.get("edited")) else 0,
    }


def _asset_fields(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "library_id": _int(item.get("library_id")),
        "document_id": _int(item.get("document_id")),
        "rel_path": str(item.get("rel_path") or "")[:500],
        "page": _int(item.get("page")),
        "sort_order": _int(item.get("sort_order")),
        "alt_text": str(item.get("alt_text") or "")[:200],
        "ocr_text": str(item.get("ocr_text") or ""),
    }


def _session_fields(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "library_id": _int(item.get("library_id")),
        "title": str(item.get("title") or "新对话")[:120],
        "created_at": _dt(item.get("created_at")),
        "updated_at": _dt(item.get("updated_at")),
    }


def _turn_fields(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_id": _int(item.get("session_id")),
        "question": str(item.get("question") or ""),
        "answer": str(item.get("answer") or ""),
        "result_json": str(item.get("result_json") or ""),
        "created_at": _dt(item.get("created_at")),
    }
