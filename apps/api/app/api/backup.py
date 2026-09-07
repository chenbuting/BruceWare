"""业务数据导出 / 导入，方便换电脑或换数据库。不含密钥。"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime
from typing import Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.local_settings import load_local_settings, save_local_settings
from app.core.response import fail, ok
from app.db.session import get_database_url, get_db
from app.kb.backup import (
    dump_kb,
    insert_kb_merge,
    insert_kb_replace,
    kb_file_entries,
    payload_has_kb,
    restore_kb_files,
    wipe_kb_files,
)
from app.kb.store import abs_path
from app.portal.models import PortalLink
from app.resume.models import ResumeDoc, ResumeInterview, ResumeInterviewMessage

router = APIRouter()
BACKUP_VERSION = 2
OLD_BACKUP_VERSION = 1
JSON_IMPORT_LIMIT = 20 * 1024 * 1024
ZIP_IMPORT_LIMIT = 512 * 1024 * 1024


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


def _dump(db: Session) -> dict[str, Any]:
    links = db.scalars(select(PortalLink).order_by(PortalLink.id.asc())).all()
    docs = db.scalars(select(ResumeDoc).order_by(ResumeDoc.id.asc())).all()
    interviews = db.scalars(select(ResumeInterview).order_by(ResumeInterview.id.asc())).all()
    messages = db.scalars(select(ResumeInterviewMessage).order_by(ResumeInterviewMessage.id.asc())).all()
    stored = load_local_settings(get_settings().repo_root).get("modules")
    modules = stored if isinstance(stored, dict) else {}
    return {
        "version": BACKUP_VERSION,
        "exported_at": datetime.utcnow().isoformat(),
        "modules": {
            "disabled": list(modules.get("disabled") or []),
            "unpinned": list(modules.get("unpinned") or []),
            "order": list(modules.get("order") or []),
        },
        "portal_links": [
            {
                "id": row.id,
                "title": row.title or "",
                "url": row.url or "",
                "remark": row.remark or "",
                "category": getattr(row, "category", "") or "",
                "created_at": _iso(row.created_at),
            }
            for row in links
        ],
        "resume_docs": [
            {
                "id": row.id,
                "title": row.title or "",
                "target_job": row.target_job or "",
                "content": row.content or "",
                "analysis": row.analysis or "",
                "intro": getattr(row, "intro", "") or "",
                "created_at": _iso(row.created_at),
                "updated_at": _iso(row.updated_at),
            }
            for row in docs
        ],
        "resume_interviews": [
            {
                "id": row.id,
                "resume_id": row.resume_id,
                "created_at": _iso(row.created_at),
            }
            for row in interviews
        ],
        "resume_interview_messages": [
            {
                "id": row.id,
                "interview_id": row.interview_id,
                "role": row.role or "",
                "content": row.content or "",
                "created_at": _iso(row.created_at),
            }
            for row in messages
        ],
        **dump_kb(db),
    }


def _as_list(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _apply_modules(payload: dict[str, Any]) -> None:
    modules = payload.get("modules")
    if not isinstance(modules, dict):
        return
    settings = get_settings()
    data = load_local_settings(settings.repo_root)
    stored = data.get("modules") if isinstance(data.get("modules"), dict) else {}
    for key in ("disabled", "unpinned", "order"):
        values = modules.get(key)
        if isinstance(values, list):
            stored[key] = [str(item) for item in values if str(item).strip()]
    data["modules"] = stored
    save_local_settings(settings.repo_root, data)


def _reset_kb_autoincrement(db: Session) -> None:
    from app.kb.models import KbAsset, KbChunk, KbDocument, KbFolder, KbLibrary, KbSession, KbSessionTurn

    _reset_autoincrement(db, "kb_libraries", KbLibrary.id)
    _reset_autoincrement(db, "kb_folders", KbFolder.id)
    _reset_autoincrement(db, "kb_documents", KbDocument.id)
    _reset_autoincrement(db, "kb_chunks", KbChunk.id)
    _reset_autoincrement(db, "kb_assets", KbAsset.id)
    _reset_autoincrement(db, "kb_sessions", KbSession.id)
    _reset_autoincrement(db, "kb_session_turns", KbSessionTurn.id)


def _reset_autoincrement(db: Session, table: str, column) -> None:
    max_id = int(db.scalar(select(func.max(column))) or 0)
    url = get_database_url() or ""
    try:
        if url.startswith("sqlite"):
            db.execute(text("DELETE FROM sqlite_sequence WHERE name = :name"), {"name": table})
            if max_id:
                db.execute(text("INSERT INTO sqlite_sequence (name, seq) VALUES (:name, :seq)"), {"name": table, "seq": max_id})
        elif "mysql" in url:
            db.execute(text(f"ALTER TABLE {table} AUTO_INCREMENT = {max_id + 1}"))
        elif "postgres" in url or "postgresql" in url:
            called = "true" if max_id > 0 else "false"
            db.execute(text(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), {max(max_id, 1)}, {called})"))
    except Exception:
        return


def _clear_business(db: Session) -> None:
    db.execute(delete(ResumeInterviewMessage))
    db.execute(delete(ResumeInterview))
    db.execute(delete(ResumeDoc))
    db.execute(delete(PortalLink))


def _insert_replace(db: Session, payload: dict[str, Any]) -> dict[str, int]:
    links = _as_list(payload.get("portal_links"))
    docs = _as_list(payload.get("resume_docs"))
    interviews = _as_list(payload.get("resume_interviews"))
    messages = _as_list(payload.get("resume_interview_messages"))
    _clear_business(db)
    for item in links:
        fields = {
            "title": str(item.get("title") or "")[:200] or "未命名",
            "url": str(item.get("url") or "")[:1000],
            "remark": str(item.get("remark") or "")[:500],
            "category": str(item.get("category") or "")[:80],
            "created_at": _dt(item.get("created_at")),
        }
        if item.get("id"):
            fields["id"] = int(item["id"])
        db.add(PortalLink(**fields))
    for item in docs:
        fields = {
            "title": str(item.get("title") or "")[:200] or "我的简历",
            "target_job": str(item.get("target_job") or "")[:200],
            "content": str(item.get("content") or ""),
            "analysis": str(item.get("analysis") or ""),
            "intro": str(item.get("intro") or ""),
            "created_at": _dt(item.get("created_at")),
            "updated_at": _dt(item.get("updated_at")),
        }
        if item.get("id"):
            fields["id"] = int(item["id"])
        db.add(ResumeDoc(**fields))
    for item in interviews:
        fields = {
            "resume_id": int(item.get("resume_id") or 0),
            "created_at": _dt(item.get("created_at")),
        }
        if item.get("id"):
            fields["id"] = int(item["id"])
        db.add(ResumeInterview(**fields))
    for item in messages:
        fields = {
            "interview_id": int(item.get("interview_id") or 0),
            "role": str(item.get("role") or "assistant")[:20],
            "content": str(item.get("content") or ""),
            "created_at": _dt(item.get("created_at")),
        }
        if item.get("id"):
            fields["id"] = int(item["id"])
        db.add(ResumeInterviewMessage(**fields))
    db.flush()
    _reset_autoincrement(db, "portal_links", PortalLink.id)
    _reset_autoincrement(db, "resume_docs", ResumeDoc.id)
    _reset_autoincrement(db, "resume_interviews", ResumeInterview.id)
    _reset_autoincrement(db, "resume_interview_messages", ResumeInterviewMessage.id)
    counts = {"portal": len(links), "resume": len(docs), "interview": len(interviews), "kb_library": 0, "kb_document": 0}
    if payload_has_kb(payload):
        counts.update(insert_kb_replace(db, payload))
        _reset_kb_autoincrement(db)
    return counts


def _insert_merge(db: Session, payload: dict[str, Any]) -> tuple[dict[str, int], dict[int, int]]:
    links = _as_list(payload.get("portal_links"))
    docs = _as_list(payload.get("resume_docs"))
    interviews = _as_list(payload.get("resume_interviews"))
    messages = _as_list(payload.get("resume_interview_messages"))
    doc_map: dict[int, int] = {}
    interview_map: dict[int, int] = {}
    for item in links:
        row = PortalLink(
            title=str(item.get("title") or "")[:200] or "未命名",
            url=str(item.get("url") or "")[:1000],
            remark=str(item.get("remark") or "")[:500],
            category=str(item.get("category") or "")[:80],
            created_at=_dt(item.get("created_at")),
        )
        db.add(row)
    db.flush()
    for item in docs:
        old_id = int(item["id"]) if item.get("id") else 0
        row = ResumeDoc(
            title=str(item.get("title") or "")[:200] or "我的简历",
            target_job=str(item.get("target_job") or "")[:200],
            content=str(item.get("content") or ""),
            analysis=str(item.get("analysis") or ""),
            intro=str(item.get("intro") or ""),
            created_at=_dt(item.get("created_at")),
            updated_at=_dt(item.get("updated_at")),
        )
        db.add(row)
        db.flush()
        if old_id:
            doc_map[old_id] = row.id
    for item in interviews:
        old_id = int(item["id"]) if item.get("id") else 0
        old_resume = int(item.get("resume_id") or 0)
        resume_id = doc_map.get(old_resume)
        if resume_id is None:
            continue
        row = ResumeInterview(resume_id=resume_id, created_at=_dt(item.get("created_at")))
        db.add(row)
        db.flush()
        if old_id:
            interview_map[old_id] = row.id
    for item in messages:
        interview_id = interview_map.get(int(item.get("interview_id") or 0))
        if interview_id is None:
            continue
        db.add(
            ResumeInterviewMessage(
                interview_id=interview_id,
                role=str(item.get("role") or "assistant")[:20],
                content=str(item.get("content") or ""),
                created_at=_dt(item.get("created_at")),
            )
        )
    counts = {"portal": len(links), "resume": len(docs), "interview": len(interviews), "kb_library": 0, "kb_document": 0}
    lib_map: dict[int, int] = {}
    if payload_has_kb(payload):
        kb_counts, lib_map = insert_kb_merge(db, payload)
        counts.update(kb_counts)
    return counts, lib_map


def _pack_zip(db: Session) -> bytes:
    payload = _dump(db)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("backup.json", json.dumps(payload, ensure_ascii=False, indent=2))
        for library_id, rel in kb_file_entries(db):
            try:
                path = abs_path(library_id, rel)
            except ValueError:
                continue
            if path.is_file():
                zf.write(path, f"files/{library_id}/{rel}")
    return buf.getvalue()


def _read_zip(raw: bytes) -> tuple[dict[str, Any], dict[tuple[int, str], bytes]]:
    blobs: dict[tuple[int, str], bytes] = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        try:
            payload = json.loads(zf.read("backup.json").decode("utf-8-sig"))
        except Exception as exc:
            raise ValueError("这个备份读不出来") from exc
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            if info.is_dir() or name == "backup.json" or ".." in name:
                continue
            if not name.startswith("files/"):
                continue
            rest = name[6:]
            parts = rest.split("/", 1)
            if len(parts) != 2 or not parts[0].isdigit() or not parts[1]:
                continue
            blobs[(int(parts[0]), parts[1])] = zf.read(info)
    if not isinstance(payload, dict):
        raise ValueError("这个备份读不出来")
    return payload, blobs


@router.get("/settings/export")
def export_backup(db: Session = Depends(get_db)):
    filename = f"bruceware-backup-{datetime.utcnow().strftime('%Y%m%d')}.zip"
    return Response(
        content=_pack_zip(db),
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote(filename)}",
        },
    )


@router.post("/settings/import")
async def import_backup(
    file: UploadFile = File(...),
    mode: Literal["replace", "merge"] = Form(default="replace"),
    db: Session = Depends(get_db),
):
    name = (file.filename or "").strip().lower()
    if name.startswith("~$") or not (name.endswith(".json") or name.endswith(".zip")):
        return fail("请上传备份文件（.zip 或旧的 .json）")
    raw = await file.read()
    if not raw:
        return fail("文件是空的")
    blobs: dict[tuple[int, str], bytes] = {}
    try:
        if name.endswith(".zip"):
            if len(raw) > ZIP_IMPORT_LIMIT:
                return fail("文件太大")
            payload, blobs = _read_zip(raw)
        else:
            if len(raw) > JSON_IMPORT_LIMIT:
                return fail("文件太大")
            payload = json.loads(raw.decode("utf-8-sig"))
    except Exception:
        return fail("这个备份读不出来")
    if not isinstance(payload, dict):
        return fail("不是这份软件的备份文件")
    try:
        version = int(payload.get("version") or 0)
    except (TypeError, ValueError):
        version = 0
    if version not in (OLD_BACKUP_VERSION, BACKUP_VERSION):
        return fail("不是这份软件的备份文件")
    try:
        lib_map: dict[int, int] | None = None
        if mode == "replace":
            counts = _insert_replace(db, payload)
        else:
            counts, lib_map = _insert_merge(db, payload)
        _apply_modules(payload)
        db.commit()
    except Exception:
        db.rollback()
        return fail("导入失败，数据没有改")
    if payload_has_kb(payload):
        if mode == "replace":
            wipe_kb_files()
        restore_kb_files(blobs, None if mode == "replace" else lib_map)
    return ok({"mode": mode, **counts})
