"""知识库接口：多库、文件夹、上传、预览、提问。"""

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from threading import Thread
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ai import chat_complete, chat_complete_stream, llm_public
from app.core.response import fail, ok
from app.db.session import get_db, new_session
from app.kb.extract import extract_search_text, extract_sheet_grid, is_sheet_name, sheet_rows_for_ask
from app.kb.flow import apply_document_all, apply_document_step, saved_parsed
from app.kb.pipeline import flow_view, remember_parsed, search_text_for_index
from app.kb.progress import mark_progress, read_progress
from app.kb.assets import (
    OCR_SKIP,
    already_extracted,
    align_ready_figure_names,
    append_asset_alts,
    attach_ready_figure_text,
    asset_dict,
    asset_edit_dict,
    document_images_pdf,
    asset_notes_for_ask,
    assets_for_ask,
    pick_assets_cited_in_answer,
    clear_assets,
    list_doc_assets,
    pack_asset_note,
    rebuild_search_text,
    save_extracted_images,
)
from app.kb.ocr import ensure_ocr
from app.kb.vision import pending_vision_count, recognize_assets, recognize_one_asset
from app.kb.models import KbAsset, KbChunk, KbDocument, KbFolder, KbLibrary
from app.kb.sessions import (
    create_session,
    delete_library_sessions,
    delete_session,
    ensure_session,
    get_session,
    list_sessions,
    load_turns,
    save_turn,
    session_dict,
)
from app.kb.policy import dump_policy, parse_policy, resolve_mode
from app.kb.search import folder_scope, search_terms, snippet_of
from app.kb.milvus_store import delete_library_vectors, take_milvus_note
from app.kb.vector import (
    chunk_dict,
    clear_chunks,
    list_chunks,
    document_vector_state,
    ensure_chunks,
    hybrid_rank,
    index_document,
    pack_ask_snippets,
    score_chunks,
    supplement_hits,
    update_chunk_text,
    vector_payload,
)
from app.kb.wiki import ASK_WIKI_LIMIT, clip_summary, dump_wiki, learn_hint, parse_wiki, wiki_item
from app.kb.store import (
    file_digest,
    kind_of,
    parse_status_of,
    remove_file,
    remove_library_dir,
    safe_filename,
    write_bytes,
    abs_path,
)

router = APIRouter()


class LibraryIn(BaseModel):
    name: str = Field(default="", max_length=120)
    description: str = Field(default="", max_length=500)


class PolicyIn(BaseModel):
    wiki_enabled: bool = False
    wiki_learn: bool = False
    vision_enabled: bool = False
    vision_engine: str = "vision"
    evidence_mode: str = "strict"
    rule: str = Field(default="", max_length=500)
    text_limit: int = 20000
    sheet_limit: int = 40000
    sheet_rows: int = 500
    clean_collapse: bool = True
    chunk_size: int = 400
    chunk_overlap: int = 60
    max_chunks: int = 40
    vector_enabled: bool = True
    link_enabled: bool = False
    link_hops: int = 3


class WikiIn(BaseModel):
    summary: str = Field(default="", max_length=800)


class AssetPatch(BaseModel):
    caption: str = Field(default="", max_length=200)
    keywords: str = Field(default="", max_length=200)
    ocr_text: str = Field(default="", max_length=1500)


class AssetBatchItem(BaseModel):
    """批量改图说明时的一张。"""

    id: int
    caption: str = Field(default="", max_length=200)
    keywords: str = Field(default="", max_length=200)
    ocr_text: str = Field(default="", max_length=1500)


class AssetBatchIn(BaseModel):
    """一次提交多张图的说明，只存字。"""

    items: list[AssetBatchItem] = Field(default_factory=list, max_length=200)


class ChunkPatch(BaseModel):
    text: str = Field(default="", max_length=8000)
    embed: bool = True


class StageIn(BaseModel):
    """手改解析或清洗结果。只存字，不自动做下一步。"""

    step: str = ""
    text: str = Field(default="", max_length=40000)


class FolderIn(BaseModel):
    name: str = Field(default="", max_length=200)
    parent_id: int | None = None


class DocumentPatch(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    tags: str | None = Field(default=None, max_length=500)
    folder_id: int | None = None
    disabled: bool | None = None


# 本页连续问只带最近几轮，不落库。
ASK_HISTORY_LIMIT = 6
# 写回答固定上限，不跟着资料变多再改。
ASK_ANSWER_TIMEOUT = 120


class AskTurnIn(BaseModel):
    """前端传来的上一轮问答，只用来听懂指代。"""

    question: str = Field(default="", max_length=2000)
    answer: str = Field(default="", max_length=8000)


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    folder_id: int | None = None
    only_folder: bool = False
    evidence_mode: str | None = None
    link_enabled: bool | None = None
    ask_kind: str = Field(default="answer", max_length=20)
    history: list[AskTurnIn] = Field(default_factory=list)
    session_id: int | None = None


class SessionIn(BaseModel):
    title: str = Field(default="", max_length=120)


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value else ""


def _library_dict(row: KbLibrary) -> dict:
    policy = parse_policy(row)
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description or "",
        "wiki_enabled": policy["wiki_enabled"],
        "wiki_learn": policy["wiki_learn"],
        "vision_enabled": policy["vision_enabled"],
        "vision_engine": policy["vision_engine"],
        "evidence_mode": policy["evidence_mode"],
        "rule": policy["rule"],
        "text_limit": policy["text_limit"],
        "sheet_limit": policy["sheet_limit"],
        "sheet_rows": policy["sheet_rows"],
        "clean_collapse": policy["clean_collapse"],
        "chunk_size": policy["chunk_size"],
        "chunk_overlap": policy["chunk_overlap"],
        "max_chunks": policy["max_chunks"],
        "vector_enabled": policy["vector_enabled"],
        "link_enabled": policy["link_enabled"],
        "link_hops": policy["link_hops"],
        "created_at": _iso(row.created_at),
    }


def _folder_dict(row: KbFolder) -> dict:
    return {
        "id": row.id,
        "library_id": row.library_id,
        "parent_id": row.parent_id,
        "name": row.name,
    }


def _doc_dict(row: KbDocument, db: Session | None = None) -> dict:
    note = parse_wiki(row)
    state = "none"
    if db is not None:
        state = document_vector_state(db, row)
    return {
        "id": row.id,
        "library_id": row.library_id,
        "folder_id": row.folder_id,
        "title": row.title or row.file_name,
        "file_name": row.file_name,
        "rel_path": row.rel_path,
        "source": row.source or "upload",
        "tags": row.tags or "",
        "file_hash": row.file_hash or "",
        "parse_status": row.parse_status or "ready",
        "kind": row.kind or "other",
        "preview": row.kind if row.kind in {"pdf", "image", "text"} else "",
        "evidence_level": row.evidence_level or "须出处",
        "has_wiki": bool(note.summary),
        "wiki_summary": note.summary,
        "wiki_updated_at": note.updated_at,
        "wiki_stale": note.stale,
        "vector_state": state,
        "disabled": bool(row.disabled),
        "flow": flow_view(row),
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def _ensure_default(db: Session) -> None:
    if db.scalar(select(KbLibrary.id).limit(1)):
        return
    row = KbLibrary(name="默认", description="")
    db.add(row)
    db.commit()


def _get_library(db: Session, library_id: int) -> KbLibrary | None:
    return db.get(KbLibrary, library_id)


def _ready_vision(lib: KbLibrary):
    """识图前检查。通过返回识别方式，否则返回错误响应。"""

    policy = parse_policy(lib)
    if not policy["vision_enabled"]:
        return None, fail("这个库还没开启识图")
    engine = policy["vision_engine"]
    if engine == "ocr":
        try:
            ensure_ocr()
        except ValueError as exc:
            return None, fail(str(exc))
        return engine, None
    if not llm_public().get("has_key"):
        return None, fail("请先在设置里填写 AI Key")
    return engine, None


def _folder_in_library(db: Session, library_id: int, folder_id: int | None) -> bool:
    if folder_id is None:
        return True
    row = db.get(KbFolder, folder_id)
    return bool(row and row.library_id == library_id)


@router.get("/kb/libraries")
def list_libraries(db: Session = Depends(get_db)):
    _ensure_default(db)
    rows = db.scalars(select(KbLibrary).order_by(KbLibrary.id.asc())).all()
    return ok({"items": [_library_dict(row) for row in rows]})


@router.post("/kb/libraries")
def create_library(body: LibraryIn, db: Session = Depends(get_db)):
    name = body.name.strip() or "未命名库"
    row = KbLibrary(name=name, description=body.description.strip())
    db.add(row)
    db.commit()
    db.refresh(row)
    return ok(_library_dict(row))


@router.put("/kb/libraries/{library_id}")
def update_library(library_id: int, body: LibraryIn, db: Session = Depends(get_db)):
    row = _get_library(db, library_id)
    if row is None:
        return fail("这个库不存在", 404)
    name = body.name.strip()
    if not name:
        return fail("请填写库名")
    row.name = name
    row.description = body.description.strip()
    db.commit()
    db.refresh(row)
    return ok(_library_dict(row))


@router.put("/kb/libraries/{library_id}/policy")
def update_library_policy(library_id: int, body: PolicyIn, db: Session = Depends(get_db)):
    """保存库规则和 Wiki 开关，不改库名。"""

    row = _get_library(db, library_id)
    if row is None:
        return fail("这个库不存在", 404)
    mode = body.evidence_mode if body.evidence_mode in {"strict", "loose"} else "strict"
    row.policy_json = dump_policy(
        body.wiki_enabled,
        mode,
        body.rule,
        body.wiki_learn,
        body.vision_enabled,
        body.vision_engine,
        body.chunk_size,
        body.chunk_overlap,
        body.text_limit,
        body.sheet_limit,
        body.sheet_rows,
        body.clean_collapse,
        body.max_chunks,
        body.vector_enabled,
        body.link_enabled,
        body.link_hops,
    )
    db.commit()
    db.refresh(row)
    return ok(_library_dict(row))


@router.get("/kb/libraries/{library_id}/wikis")
def list_wikis(
    library_id: int,
    q: str = "",
    stale: str = "",
    sort: str = "updated_at",
    order: str = "desc",
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
):
    """管理库里的摘要列表，分页，不一次拉全量。"""

    if _get_library(db, library_id) is None:
        return fail("这个库不存在", 404)
    size = min(max(page_size, 1), 50)
    current = max(page, 1)
    rows = db.scalars(select(KbDocument).where(KbDocument.library_id == library_id, KbDocument.wiki_json != "")).all()
    notes = []
    for row in rows:
        note = parse_wiki(row)
        if note.summary:
            notes.append((row, note))
    all_count = len(notes)
    stale_count = sum(1 for _, note in notes if note.stale)
    query = q.strip().lower()
    if query:
        notes = [item for item in notes if query in (item[0].title or item[0].file_name or "").lower()]
    if stale == "stale":
        notes = [item for item in notes if item[1].stale]
    elif stale == "fresh":
        notes = [item for item in notes if not item[1].stale]
    reverse = order != "asc"
    if sort == "title":
        notes.sort(key=lambda item: (item[0].title or item[0].file_name or "").lower(), reverse=reverse)
    elif sort == "stale":
        notes.sort(key=lambda item: (item[1].stale, item[1].updated_at), reverse=reverse)
    else:
        notes.sort(key=lambda item: item[1].updated_at, reverse=reverse)
    total = len(notes)
    start = (current - 1) * size
    page_rows = notes[start : start + size]
    return ok(
        {
            "items": [wiki_item(row, note) for row, note in page_rows],
            "total": total,
            "page": current,
            "page_size": size,
            "all_count": all_count,
            "stale_count": stale_count,
        }
    )


@router.delete("/kb/libraries/{library_id}")
def delete_library(library_id: int, db: Session = Depends(get_db)):
    row = _get_library(db, library_id)
    if row is None:
        return fail("这个库不存在", 404)
    delete_library_sessions(db, library_id)
    db.execute(KbAsset.__table__.delete().where(KbAsset.library_id == library_id))
    db.execute(KbChunk.__table__.delete().where(KbChunk.library_id == library_id))
    db.execute(KbDocument.__table__.delete().where(KbDocument.library_id == library_id))
    db.execute(KbFolder.__table__.delete().where(KbFolder.library_id == library_id))
    db.delete(row)
    db.commit()
    delete_library_vectors(library_id)
    remove_library_dir(library_id)
    _ensure_default(db)
    return ok(True)


@router.get("/kb/libraries/{library_id}/folders")
def list_folders(library_id: int, db: Session = Depends(get_db)):
    if _get_library(db, library_id) is None:
        return fail("这个库不存在", 404)
    rows = db.scalars(select(KbFolder).where(KbFolder.library_id == library_id).order_by(KbFolder.id.asc())).all()
    return ok({"items": [_folder_dict(row) for row in rows]})


@router.post("/kb/libraries/{library_id}/folders")
def create_folder(library_id: int, body: FolderIn, db: Session = Depends(get_db)):
    if _get_library(db, library_id) is None:
        return fail("这个库不存在", 404)
    name = body.name.strip()
    if not name:
        return fail("请填写文件夹名")
    parent_id = body.parent_id
    if parent_id is not None and not _folder_in_library(db, library_id, parent_id):
        return fail("上级文件夹不在这个库里")
    exists = db.scalar(
        select(KbFolder.id).where(
            KbFolder.library_id == library_id,
            KbFolder.parent_id == parent_id,
            KbFolder.name == name,
        )
    )
    if exists:
        return fail("同一层已有同名文件夹")
    row = KbFolder(library_id=library_id, parent_id=parent_id, name=name)
    db.add(row)
    db.commit()
    db.refresh(row)
    return ok(_folder_dict(row))


@router.put("/kb/folders/{folder_id}")
def rename_folder(folder_id: int, body: FolderIn, db: Session = Depends(get_db)):
    row = db.get(KbFolder, folder_id)
    if row is None:
        return fail("文件夹不存在", 404)
    name = body.name.strip()
    if not name:
        return fail("请填写文件夹名")
    exists = db.scalar(
        select(KbFolder.id).where(
            KbFolder.library_id == row.library_id,
            KbFolder.parent_id == row.parent_id,
            KbFolder.name == name,
            KbFolder.id != row.id,
        )
    )
    if exists:
        return fail("同一层已有同名文件夹")
    row.name = name
    db.commit()
    db.refresh(row)
    return ok(_folder_dict(row))


@router.delete("/kb/folders/{folder_id}")
def delete_folder(folder_id: int, db: Session = Depends(get_db)):
    row = db.get(KbFolder, folder_id)
    if row is None:
        return fail("文件夹不存在", 404)
    has_child = db.scalar(select(KbFolder.id).where(KbFolder.parent_id == folder_id).limit(1))
    has_doc = db.scalar(select(KbDocument.id).where(KbDocument.folder_id == folder_id).limit(1))
    if has_child or has_doc:
        return fail("文件夹里还有内容，请先移走或删掉")
    db.delete(row)
    db.commit()
    return ok(True)


@router.get("/kb/libraries/{library_id}/documents")
def list_documents(
    library_id: int,
    folder_id: int | None = None,
    q: str = "",
    tag: str = "",
    db: Session = Depends(get_db),
):
    if _get_library(db, library_id) is None:
        return fail("这个库不存在", 404)
    stmt = select(KbDocument).where(KbDocument.library_id == library_id)
    query = q.strip()
    tag_text = tag.strip()
    if query or tag_text:
        if folder_id is not None:
            stmt = stmt.where(KbDocument.folder_id == folder_id)
    else:
        stmt = stmt.where(KbDocument.folder_id == folder_id)
    rows = db.scalars(stmt.order_by(KbDocument.updated_at.desc())).all()
    items = []
    for row in rows:
        if query:
            blob = f"{row.title} {row.file_name} {row.tags}".lower()
            if query.lower() not in blob:
                continue
        if tag_text and tag_text not in (row.tags or ""):
            continue
        items.append(_doc_dict(row, db))
    if db.dirty:
        db.commit()
    return ok({"items": items})


@router.get("/kb/progress/{job}")
def job_progress(job: str):
    """出稿或导入进行中，页面来问走到哪一步了。"""

    return ok(read_progress(job))


@router.post("/kb/ready-draft")
async def ready_draft(file: UploadFile = File(...), job: str = Form(default="")):
    """按这份文件出一份可检查的整理稿。不入库，不切片，不算向量。"""

    from app.kb.ready_fill import draft_bytes

    data = await file.read()
    if not data:
        return fail("文件是空的")
    name = safe_filename(file.filename or "未命名")

    def work():
        def tell(text: str, current: int, total: int) -> None:
            mark_progress(job, text, current, total)

        return draft_bytes(name, data, tell)

    try:
        blob, summary = await asyncio.to_thread(work)
    except ValueError as exc:
        return fail(str(exc))
    stem = Path(name).stem or "整理稿"
    filename = quote(f"{stem}-图字.docx")
    mark_progress(job, "稿已写好", 1, 1)
    return Response(
        content=blob,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
            "X-Kb-Name": filename,
            "X-Kb-Note": quote(summary),
        },
    )


@router.post("/kb/libraries/{library_id}/documents")
async def upload_document(
    library_id: int,
    file: UploadFile = File(...),
    folder_id: int | None = Form(default=None),
    tags: str = Form(default=""),
    force: bool = Form(default=False),
    ready: bool = Form(default=False),
    job: str = Form(default=""),
):
    data = await file.read()
    file_name = safe_filename(file.filename or "未命名")

    def work():
        db = new_session()
        try:
            return _store_uploaded_document(db, library_id, data, file_name, folder_id, tags, force, ready, job)
        finally:
            db.close()

    return await asyncio.to_thread(work)


def _store_uploaded_document(
    db: Session,
    library_id: int,
    data: bytes,
    file_name: str,
    folder_id: int | None,
    tags: str,
    force: bool,
    ready: bool,
    job: str,
):
    """保存文件并按普通导入或整理稿导入处理。进度只是旁路，不改变结果。"""

    lib = _get_library(db, library_id)
    if lib is None:
        return fail("这个库不存在", 404)
    if not _folder_in_library(db, library_id, folder_id):
        return fail("文件夹不在这个库里")
    if not data:
        return fail("文件是空的")
    steps = 6 if ready else 2
    mark_progress(job, "正在保存文件", 1, steps)
    digest = file_digest(data)
    existing = db.scalar(
        select(KbDocument).where(KbDocument.library_id == library_id, KbDocument.file_hash == digest)
    )
    if existing and not force:
        return fail(f"库里已有相同文件「{existing.title or existing.file_name}」，确认后可另存")
    kind = kind_of(file_name)
    policy = parse_policy(lib)
    row = KbDocument(
        library_id=library_id,
        folder_id=folder_id,
        title=file_name,
        file_name=file_name,
        rel_path="",
        source="upload",
        tags=tags.strip(),
        file_hash=digest,
        parse_status=parse_status_of(kind),
        kind=kind,
        search_text=search_text_for_index(file_name, data, policy),
        extra="",
        sheet_json=extract_sheet_grid(file_name, data, policy["sheet_rows"]),
        updated_at=datetime.utcnow(),
    )
    db.add(row)
    db.flush()
    rel_path = f"{row.id}_{file_name}"
    write_bytes(library_id, rel_path, data)
    row.rel_path = rel_path
    alts = save_extracted_images(db, row, data)
    remember_parsed(row, extract_search_text(file_name, data, collapse=False))
    append_asset_alts(row, alts)
    ready_status = ""
    if ready:
        def on_step(step: str) -> None:
            label, current = _READY_PROGRESS[step]
            mark_progress(job, label, current, steps)

        align_ready_figure_names(db, row, data)
        ready_status, _quality = apply_document_all(db, row, _READY_FLOW, on_step=on_step)
        if ready_status == "failed" or ready_status.startswith(("failed", "parse_failed", "clean_failed")):
            remove_file(library_id, rel_path)
            db.rollback()
            return fail("整理稿没导入成。请确认已经排成普通段落。")
        mark_progress(job, "正在挂上图里的字", 6, steps)
        attach_ready_figure_text(db, row, saved_parsed(row))
    else:
        mark_progress(job, "正在放入库里", 1, steps)
        index_document(db, row)
    db.commit()
    db.refresh(row)
    data = _doc_dict(row, db)
    note = take_milvus_note()
    if ready_status:
        data["vector_hint"] = _READY_HINTS.get(ready_status, "已按整理稿导入。")
    elif note:
        data["vector_hint"] = note
    mark_progress(job, "已经放进库里", steps, steps)
    return ok(data)


# 整理稿仍用现在的默认抽法。切片放到 64 段，两万字正文加上标题也能切完。
_READY_FLOW = {
    "parse": "standard",
    "parse_hint": "",
    "parse_script": "",
    "cleans": ["collapse"],
    "rules": [],
    "script": "",
    "chunk": "chars",
    "vector": True,
    "chunk_size": 400,
    "chunk_overlap": 60,
    "max_chunks": 64,
}
_READY_PROGRESS = {
    "parse": ("正在解析", 2),
    "clean": ("正在清洗", 3),
    "chunk": ("正在切片", 4),
    "vector": ("正在算向量", 5),
}
_READY_HINTS = {
    "done": "已按整理稿导入，解析、清洗、切片和向量都做完了。",
    "done_keywords": "已按整理稿导入。这一份只按关键词，没有算向量。",
    "no_key": "已按整理稿导入。还没填 AI Key，向量没算。",
}


def _fill_search_text(row: KbDocument, db: Session, force: bool = False) -> None:
    """旧文件还没抽过正文时补一次。表格每次按新规则重抽。force 时按本库设置重抽。"""

    sheet = is_sheet_name(row.file_name)
    if not force and not sheet and (row.search_text or "").strip():
        return
    try:
        path = abs_path(row.library_id, row.rel_path)
        data = path.read_bytes()
    except (ValueError, OSError):
        return
    lib = db.get(KbLibrary, row.library_id)
    policy = parse_policy(lib) if lib is not None else None
    text = search_text_for_index(row.file_name, data, policy)
    if force or sheet or not (row.search_text or "").strip():
        row.search_text = text
    if sheet:
        grid = extract_sheet_grid(row.file_name, data, None if policy is None else policy["sheet_rows"])
        if grid:
            row.sheet_json = grid


def _fill_assets(row: KbDocument, db: Session, force: bool = False) -> None:
    """旧文件还没抽过图时补抽。force 时再扫一遍，只补缺的图。"""

    if already_extracted(row) and not force:
        return
    try:
        path = abs_path(row.library_id, row.rel_path)
        data = path.read_bytes()
    except (ValueError, OSError):
        return
    alts = save_extracted_images(db, row, data)
    append_asset_alts(row, alts)


def _learn_wikis(question: str, doc_ids: list[int], db: Session) -> str:
    """按这次出处更新摘要。没出处不提示；一次最多 5 份。"""

    if not doc_ids:
        return ""
    truncated = len(doc_ids) > ASK_WIKI_LIMIT
    titles: list[str] = []
    for doc_id in doc_ids[:ASK_WIKI_LIMIT]:
        row = db.get(KbDocument, doc_id)
        if row is None:
            continue
        snippet = snippet_of(question, row)
        if not (snippet or "").strip():
            continue
        old = parse_wiki(row).summary
        try:
            text = chat_complete(
                [
                    {"role": "system", "content": "你根据原文和这次提问改短摘要，只写原文里有的内容。"},
                    {
                        "role": "user",
                        "content": (
                            f"用大约250字写这份资料是什么、和这次问题相关的要点看哪。不要编造。\n"
                            f"问题：{question}\n旧摘要：{old or '无'}\n标题：{row.title or row.file_name}\n\n{snippet}"
                        ),
                    },
                ],
                timeout=40,
            )
        except ValueError:
            continue
        clipped = clip_summary(text)
        if not clipped:
            continue
        row.wiki_json = dump_wiki(clipped, row.file_hash or "")
        row.updated_at = datetime.utcnow()
        titles.append(row.title or row.file_name)
    if titles:
        db.commit()
    return learn_hint(len(doc_ids), titles, truncated)


def _learn_wikis_job(question: str, doc_ids: list[int]) -> None:
    """后台写摘要，自己开库，不挡提问返回。"""

    db = new_session()
    try:
        _learn_wikis(question, doc_ids, db)
    except Exception:
        db.rollback()
    finally:
        db.close()


def _ask_kind(raw: str | None) -> str:
    """提问方式：回答、核对清单、拿资料。其它值当回答。"""

    value = (raw or "").strip()
    if value in {"checklist", "materials"}:
        return value
    return "answer"


_MATERIAL_SKIP = {
    "给我",
    "一下",
    "帮我",
    "请把",
    "原件",
    "资料",
    "文件",
    "这个",
    "那个",
    "相关",
    "所有",
    "全部",
    "看看",
    "出来",
    "有没有",
    "没有",
    "有吗",
    "是不是",
}


def _doc_name(row) -> str:
    return f"{row.title or ''} {row.file_name or ''} {row.tags or ''}".lower()


def _material_terms(question: str) -> tuple[list[str], list[str]]:
    """只从这一句拿年份和词。25年按 2025 年理解。"""

    text = question or ""
    years = re.findall(r"(?:19|20)\d{2}", text)
    for short in re.findall(r"(?<!\d)(\d{2})年", text):
        number = int(short)
        full = str(2000 + number) if number <= 39 else str(1900 + number)
        if full not in years:
            years.append(full)
    terms: list[str] = []
    for part in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        for piece in re.split(r"[的了把将要和与及]", part):
            word = piece.strip()
            changed = True
            while changed and word:
                changed = False
                for stop in _MATERIAL_SKIP:
                    if word.startswith(stop):
                        word = word[len(stop) :]
                        changed = True
                    if word.endswith(stop):
                        word = word[: -len(stop)]
                        changed = True
            if len(word) >= 2 and word not in _MATERIAL_SKIP and word not in terms:
                terms.append(word)
    terms.sort(key=len, reverse=True)
    return years, terms[:8]


def _followup_years(question: str, prev: str) -> list[str]:
    """上一句在谈某一年时，这一句里的 25 按 2025 年理解。"""

    if not prev or not _material_terms(prev)[0]:
        return []
    years: list[str] = []
    for short in re.findall(r"(?<!\d)(\d{2})(?!\d)", question or ""):
        number = int(short)
        if number > 39:
            continue
        full = str(2000 + number)
        if full not in years:
            years.append(full)
    return years


def _focus_material(question: str, search_q: str) -> tuple[str, list[str]]:
    """听懂这一句要的那一份。换了年份就不要再带上一句的年份。"""

    prev = ""
    if "\n" in (search_q or ""):
        head = search_q.split("\n", 1)[0].strip()
        if head and head != (question or "").strip():
            prev = head
    years, _terms = _material_terms(question)
    if not years:
        years = _followup_years(question, prev)
    focused = ""
    if llm_public().get("has_key"):
        try:
            text = chat_complete(
                [
                    {"role": "system", "content": "你只把这一句要的资料说清楚，不回答问题。"},
                    {
                        "role": "user",
                        "content": (
                            "上一句只用来听懂「还有、那个、也要」指哪一类资料。"
                            "只写这一句要的那一份：年份写成四位数，资料用文件名里可能出现的叫法。"
                            "这一句换了年份，就不要写上一句的年份。"
                            "不要解释。不超过40字。\n\n"
                            f"上一句：{prev or '无'}\n这一句：{question}"
                        ),
                    },
                ],
                timeout=18,
            )
            focused = " ".join((text or "").split())[:80]
        except Exception:
            focused = ""
    heard, _heard_terms = _material_terms(focused)
    if not years:
        years = heard
    query = focused or question
    for year in years:
        if year not in query:
            query = f"{query}\n{year}"
    return query, years


def _materials_choose(question: str, search_q: str, rows: list, chunk_best: dict) -> tuple[list, bool, list[str]]:
    """按语义和向量挑。这一句要了哪一年，就去掉另一年。"""

    query, years = _focus_material(question, search_q)
    ranked = hybrid_rank(query, rows, chunk_best, top_k=8)
    used_vector = bool(chunk_best)
    picked: list[tuple[object, float]] = []
    for row, score, _pieces in ranked:
        found = re.findall(r"(?:19|20)\d{2}", _doc_name(row))
        if years and found and not any(year in found for year in years):
            continue
        picked.append((row, score))
    if years:
        exact = [(row, score) for row, score in picked if any(year in _doc_name(row) for year in years)]
        if exact:
            picked = exact
    if not picked:
        return [], used_vector, years
    best = picked[0][1]
    floor = max(0.28, best * 0.72)
    kept = [row for row, score in picked if score >= floor]
    return kept[:3], used_vector, years


def _materials_early(db: Session, question: str, search_q: str, rows: list, chunk_best: dict) -> dict:
    """拿资料：用语义和向量找文件，不看严格或宽松，也不写成回答。"""

    picked, used_vector, years = _materials_choose(question, search_q, rows, chunk_best)
    for row in picked:
        _fill_assets(row, db)
    if db.dirty:
        db.commit()
    how = "按语义和向量找的" if used_vector else "按关键词找的，向量没参与"
    asked = f"只要 {'、'.join(years)} 年的。" if years else ""
    if not picked:
        return {
            "answer": f"没有对上的资料。{asked}{how}。",
            "citations": [],
            "used_llm": False,
            "evidence_mode": "",
            "wiki_update_hint": "",
            "used_vector": used_vector,
            "ask_kind": "materials",
        }
    citations = []
    lines = [f"找到 {len(picked)} 份。{asked}{how}，按文件分开交给你。"]
    for index, row in enumerate(picked, start=1):
        pictures = [asset_dict(item) for item in list_doc_assets(db, row.id)]
        title = row.title or row.file_name
        citations.append({"id": row.id, "title": title, "score": 1, "images": pictures})
        if pictures:
            lines.append(f"{index}. {title}：图 {len(pictures)} 张。")
        else:
            lines.append(f"{index}. {title}：没有抽出图，可以打开原件。")
    return {
        "answer": "\n".join(lines),
        "citations": citations,
        "used_llm": False,
        "evidence_mode": "",
        "wiki_update_hint": "",
        "used_vector": used_vector,
        "ask_kind": "materials",
    }

def _meaning_rule() -> str:
    """按事情类别判断，不靠问句和原文几个字是否相同。"""

    return (
        "判断靠事情的类别，不靠几个字是否相同。"
        "禁止因为原文没出现问句里的原词就报【缺失】或未命中。"
        "原文用了别的叫法，但说的是问的那一类事情，必须当见到，写出原文里的叫法和内容。"
        "只有原文自己标明是另一类用途时，才不能顶替。"
    )


def _conflict_rule(*, pick: bool) -> str:
    """本轮资料打架时必须标出来，不许只报一条。"""

    judge = (
        "可以写更像哪一处，但必须标【推断】，并写「以下为推断，请以原文核对」。"
        if pick
        else "不要自行裁定哪个对，不要只报其中一个。"
    )
    return (
        "本轮资料（正文、切片、图上的说明）对同一事实出现不同写法时，"
        "例如同一项住所、同一项日期、同一项名称、同一项金额不一致，必须标【冲突】，"
        "把各处原文和出处都列出来（资料序号、文件名；用到图就写图号）。"
        "原文标明是不同用途、不同名目的两项，分开答，不要标【冲突】。"
        + judge
    )


def _checklist_style() -> str:
    """清单模式：只出要素表，不下结论。"""

    return (
        "你在做核对清单，不是回答是否合规、能不能过。"
        "先按问句拆出要核对的要素，大约 3 到 8 项。"
        "对每一项只根据本轮资料写：要素、命中或未命中或冲突、出处（资料序号、文件名；用到图上的字就写图号，如图56）。"
        "本轮见到且说法一致写命中，本轮没见到写未命中；同一要素出现不同写法写冲突，不要写成命中。"
        + _conflict_rule(pick=False)
        + "不要写整个库都没有，不要写已穷举，不要编第几章、第几页。"
        "不要写可以通过、存在风险、建议批准这类结论。"
        "用 Markdown 表格，表头为：要素 | 状态 | 出处 | 本轮见到的原文摘要。"
        "摘要没有就写—。冲突时摘要里并列各处原文。不要插入图片。"
        "没用上的资料不要写进表，也不要写进出处。"
        "表结束后另起一行写：本表只展示本轮检索命中情况，合不合格请对照原文自行判断。"
    )


def _ask_style(mode: str, rule: str) -> str:
    """拼给模型的回答约束。"""

    if mode == "loose":
        text = (
            "可以参考摘要帮助概括，但必须标明来自哪份资料。图上认下来的图意和字也算出处。"
            "先写一句结论。有本轮原文就贴一两句，用引用块。"
            "对得上原文标【确凿】；只能根据上下文推测时标【推断】，并写「以下为推断，请以原文核对」；本轮没见到标【缺失】，写当前检索到的内容中未找到，建议查阅原文。"
            + _conflict_rule(pick=True)
            + "不要说整个库都没有。不要编页码、章节。"
        )
    else:
        text = (
            "必须依据原文片段和图上认下来的图意、文字作答，不能把摘要当证据。可以说见哪张图。"
            "先写一句结论。有本轮原文就贴一两句，用引用块。出处写文件名，有图号写图号，不要编页码、章节。"
            "对得上原文标【确凿】；本轮没见到标【缺失】，写当前检索到的内容中未找到，建议查阅原文确认。"
            + _conflict_rule(pick=False)
            + "严格模式禁止【推断】，禁止「可能」。不要说整个库都没有。"
        )
    extra = (rule or "").strip()
    if extra:
        text += f" 额外规则：{extra}"
    text += (
        "按正常对话作答：先把问题听懂，用合适的方式说清楚，并标明出处。"
        "不要每次都套「要素 / 状态 / 出处」那种固定清单格式。"
        "用户要表格、对比或列举时，可以用普通表格或列表，格式跟着问句走，不要锁死一种模板。"
        + _meaning_rule()
        + "问句里的简称和资料里的全称对得上就视为同一类，不要只因用词不完全一样就说没有。"
        "若要展示图，把资料里「可展示的图」那一行 ![说明](地址) 原样插到对应句子旁边，不要改地址。"
        "不需要配图就不要插入图片。"
    )
    return text


def _ask_history(items: list[AskTurnIn]) -> list[AskTurnIn]:
    """只留最近几轮里问、答都有的。当前这句另算，所以最多再带 5 轮。"""

    cleaned: list[AskTurnIn] = []
    for item in items:
        question = item.question.strip()
        answer = item.answer.strip()
        if question and answer:
            cleaned.append(AskTurnIn(question=question, answer=answer[:4000]))
    return cleaned[-(ASK_HISTORY_LIMIT - 1) :]


def _search_question(question: str, history: list[AskTurnIn]) -> str:
    """检索用上一句加这句，方便听懂「那有效期呢」。"""

    prev = history[-1].question if history else ""
    if prev and prev != question:
        return f"{prev}\n{question}"
    return question


def _rewrite_search(question: str) -> str:
    """按这句问话的意思补检索说法，不写死对照表。失败就仍用原句。"""

    q = (question or "").strip()
    if not q or not llm_public().get("has_key"):
        return q
    try:
        text = chat_complete(
            [
                {"role": "system", "content": "你只改写检索用语，不回答问题，不编造事实。"},
                {
                    "role": "user",
                    "content": (
                        "按意思写出这类事实在资料里可能怎么写，方便检索。"
                        "不要只重复问句里的原词，也不要写成固定对照表。"
                        "不要编造号码、地址、日期。不要解释。不超过80字。\n\n"
                        f"{q}"
                    ),
                },
            ],
            timeout=18,
        )
    except Exception:
        return q
    extra = " ".join((text or "").split())
    if not extra:
        return q
    return f"{q}\n{extra[:160]}"


def _ask_messages(question: str, prompt: str, history: list[AskTurnIn], ask_kind: str = "answer") -> list[dict]:
    """历史只帮听懂指代，证据仍是本轮资料。"""

    if ask_kind == "checklist":
        role = (
            "你是知识库核对助手。只根据本轮资料做要素清单，不下结论。"
            "用户可能接着上一句问。刚才的对话只用来听懂「那」「刚才」「这份」指什么。"
            "编号、日期、金额等必须依据本轮资料。简称和全称对得上就视为同一类。"
            + _meaning_rule()
            + "同一事实出现不同写法必须标冲突，把各处原文和出处都列出，不要只报一条，也不要裁定哪个对。"
            "原文标明用途不同的两项分开写，不要标冲突。"
            "本轮没见到就写未命中，不要说整个库都没有或已穷举，也不要编第几章、第几页。"
        )
    else:
        role = (
            "你是知识库助手，按正常对话作答，并标明出处。"
            "不要每次都套同一种固定表格。用户要表就出普通表，要一句话就说一句话，不要照抄上一轮格式。"
            "用户可能接着上一句问。刚才的对话只用来听懂「那」「刚才」「这份」指什么。"
            "编号、日期、金额、开户行、证书名称等事实必须依据本轮资料，不能拿上一轮回答当证据。"
            + _meaning_rule() +
            "简称和全称对得上就视为同一类。"
            "同一事实出现不同写法必须标【冲突】，把各处原文和出处都列出，不要只报一条。"
            "原文标明用途不同的两项分开写，不要标冲突。"
            "先结论，有原文就引用一两句。分级规则看下面的回答约束。"
            "本轮检索到的内容里没有依据，就说当前检索到的内容中未找到，建议查阅原文确认，不要说整个库都没有，也不要编第几章、第几页。"
        )
    messages = [
        {
            "role": "system",
            "content": role,
        }
    ]
    for turn in history:
        messages.append({"role": "user", "content": turn.question})
        messages.append({"role": "assistant", "content": turn.answer})
    messages.append({"role": "user", "content": f"问题：{question}\n\n{prompt}"})
    return messages


def _save_ask(db, library_id: int, session_id: int | None, question: str, payload: dict) -> dict:
    """回答成功后写入当前会话，失败的提问不建空会话。"""

    session = ensure_session(db, library_id, session_id, question)
    save_turn(db, session, question, payload)
    payload["session_id"] = session.id
    return payload


def _finish_ask(db, library_id: int, session_id: int | None, question: str, payload: dict):
    return ok(_save_ask(db, library_id, session_id, question, payload))


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


def _fill_cited_images(citations: list, ranked_full: list, note_pics: dict, show_pics: dict, answer: str, ask_kind: str) -> None:
    pool = []
    for row, _score, _snip in ranked_full:
        pool.extend(note_pics.get(row.id, []))
        if ask_kind != "checklist":
            pool.extend(show_pics.get(row.id, []))
    cited = pick_assets_cited_in_answer(pool, answer)
    by_doc: dict[int, list] = {}
    for item in cited:
        by_doc.setdefault(item.document_id, []).append(item)
    for hit in citations:
        hit["images"] = [asset_dict(item) for item in by_doc.get(hit["id"], [])]


@router.get("/kb/libraries/{library_id}/sessions")
def list_library_sessions(library_id: int, db: Session = Depends(get_db)):
    if _get_library(db, library_id) is None:
        return fail("这个库不存在", 404)
    return ok({"items": [session_dict(row) for row in list_sessions(db, library_id)]})


@router.post("/kb/libraries/{library_id}/sessions")
def create_library_session(library_id: int, body: SessionIn, db: Session = Depends(get_db)):
    if _get_library(db, library_id) is None:
        return fail("这个库不存在", 404)
    row = create_session(db, library_id, body.title)
    db.commit()
    db.refresh(row)
    return ok(session_dict(row))


@router.get("/kb/sessions/{session_id}")
def get_library_session(session_id: int, db: Session = Depends(get_db)):
    row = get_session(db, session_id)
    if row is None:
        return fail("这段对话不存在", 404)
    data = session_dict(row)
    data["turns"] = load_turns(db, row.id)
    return ok(data)


@router.put("/kb/sessions/{session_id}")
def rename_library_session(session_id: int, body: SessionIn, db: Session = Depends(get_db)):
    row = get_session(db, session_id)
    if row is None:
        return fail("这段对话不存在", 404)
    title = body.title.strip() or "新对话"
    row.title = title[:120]
    db.commit()
    db.refresh(row)
    return ok(session_dict(row))


@router.delete("/kb/sessions/{session_id}")
def delete_library_session(session_id: int, db: Session = Depends(get_db)):
    row = get_session(db, session_id)
    if row is None:
        return fail("这段对话不存在", 404)
    delete_session(db, row)
    return ok(True)


def _client_stopped(request: Request) -> bool:
    """浏览器已经点了终止，这次回答不要再写入对话。"""

    try:
        import anyio

        return bool(anyio.from_thread.run(request.is_disconnected))
    except Exception:
        return False


def _compact_query(text: str) -> str:
    return " ".join((text or "").lower().split())


def _link_evidence(ranked_full: list) -> str:
    """把这一轮已经拿到的原文收成一段，给下一跳判断用。"""

    parts = []
    total = 0
    for row, _score, snippet in ranked_full:
        piece = f"{row.title or row.file_name}\n{(snippet or '')[:800]}"
        if total + len(piece) > 5000:
            break
        parts.append(piece)
        total += len(piece)
    return "\n\n".join(parts)


def _query_has_bridge(question: str, evidence: str, query: str) -> bool:
    """下一跳必须带上原文里新出现的人名、编号或名称，不能只重复问句。"""

    ev = evidence.lower()
    asked = question.lower()
    for term in search_terms(query):
        if term in ev and term not in asked:
            return True
    return False


def _link_next_query(question: str, evidence: str) -> str:
    """看现有原文够不够。不够就返回下一跳检索词。失败或够了就返回空。"""

    if not evidence.strip():
        return ""
    try:
        text = chat_complete(
            [
                {"role": "system", "content": "你只判断资料够不够回答，不回答问题，不编造事实。"},
                {
                    "role": "user",
                    "content": (
                        "看下面的资料够不够回答问题。"
                        "够了就只写：够了。"
                        "不够，而且资料里出现了问题里没有的人名、编号、公司名或证件名，才可以再查。"
                        "只写一行：再查：检索词。"
                        "检索词必须带上资料里的那个原词，可以加上问题要查的事项。不要编造号码和日期。不超过30字。\n\n"
                        f"问题：{question}\n\n资料：\n{evidence}"
                    ),
                },
            ],
            timeout=18,
        )
    except Exception:
        return ""
    match = re.search(r"再查[：:]\s*(\S.*)", text or "")
    if not match:
        return ""
    query = " ".join(match.group(1).split())[:40]
    if not _query_has_bridge(question, evidence, query):
        return ""
    return query


def _merge_ranked(base: list, extra: list) -> list | None:
    """补查结果并进已有资料。新文件附在后面，同一份有新段落就接上。没有新字就返回空。"""

    order = [row.id for row, _score, _snippet in base]
    by_id = {row.id: (row, score, snippet) for row, score, snippet in base}
    changed = False
    for row, score, snippet in extra:
        text = (snippet or "").strip()
        if not text:
            continue
        old = by_id.get(row.id)
        if old is None:
            if len(order) >= 12:
                continue
            by_id[row.id] = (row, score, text)
            order.append(row.id)
            changed = True
            continue
        if text in (old[2] or ""):
            continue
        by_id[row.id] = (old[0], max(old[1], score), f"{old[2]}\n{text}")
        changed = True
    if not changed:
        return None
    return [by_id[item_id] for item_id in order]


def _link_follow(question: str, search_q: str, rows: list, ranked_full: list, library_id: int, db, hops: int):
    """开了关联补查才走。够回答、没有新原词、或结果没变就停。跳数只是上限。"""

    merged = list(ranked_full)
    linked: set[int] = set()
    used_vector = False
    seen = {_compact_query(search_q), _compact_query(question)}
    for _step in range(max(0, hops)):
        query = _link_next_query(question, _link_evidence(merged))
        key = _compact_query(query)
        if not key or key in seen:
            break
        seen.add(key)
        doc_ids = {row.id for row in rows}
        chunk_best = score_chunks(db, library_id, query, doc_ids)
        used_vector = used_vector or bool(chunk_best)
        found = pack_ask_snippets(
            query, supplement_hits(query, rows, hybrid_rank(query, rows, chunk_best), chunk_best)
        )
        nxt = _merge_ranked(merged, found)
        if nxt is None:
            break
        before = {row.id: snippet for row, _score, snippet in merged}
        merged = nxt
        for row, _score, snippet in merged:
            if before.get(row.id) != snippet:
                linked.add(row.id)
    return merged, used_vector, linked


def _prepare_ask(library_id: int, body: AskIn, db):
    """先检索、拼提示。early 有值就不用喊模型。"""

    lib = _get_library(db, library_id)
    if lib is None:
        return None, fail("这个库不存在", 404)
    if body.only_folder and body.folder_id is not None and not _folder_in_library(db, library_id, body.folder_id):
        return None, fail("文件夹不在这个库里")
    question = body.question.strip()
    if not question:
        return None, fail("请先写问题")
    ask_kind = _ask_kind(body.ask_kind)
    folders = db.scalars(select(KbFolder).where(KbFolder.library_id == library_id)).all()
    scope = folder_scope(list(folders), body.folder_id) if body.only_folder else None
    stmt = select(KbDocument).where(KbDocument.library_id == library_id)
    rows = list(db.scalars(stmt).all())
    if scope is not None:
        rows = [row for row in rows if row.folder_id in scope]
    rows = [row for row in rows if not row.disabled]
    history = _ask_history(body.history)
    search_q = _rewrite_search(_search_question(question, history))
    for row in rows:
        _fill_search_text(row, db)
        _fill_assets(row, db)
        index_document(db, row)
    db.commit()
    chunk_best = score_chunks(db, library_id, search_q, {row.id for row in rows})
    if ask_kind == "materials":
        return {"early": _materials_early(db, question, search_q, rows, chunk_best), "question": question}, None
    policy = parse_policy(lib)
    mode = resolve_mode(policy["evidence_mode"], body.evidence_mode)
    ranked_full = pack_ask_snippets(
        search_q, supplement_hits(search_q, rows, hybrid_rank(search_q, rows, chunk_best), chunk_best)
    )
    used_vector = bool(chunk_best)
    linked: set[int] = set()
    link_on = policy["link_enabled"] if body.link_enabled is None else bool(body.link_enabled)
    if link_on and ranked_full and llm_public().get("has_key"):
        ranked_full, more_vector, linked = _link_follow(
            question, search_q, rows, ranked_full, library_id, db, int(policy["link_hops"])
        )
        used_vector = used_vector or more_vector
    ranked = [(row, score) for row, score, _snippet in ranked_full]
    citations = []
    blocks = []
    use_notes = policy["wiki_enabled"] and mode == "loose"
    note_pics, show_pics = assets_for_ask(db, [row.id for row, _score, _snip in ranked_full], search_q)
    for index, (row, score, snippet) in enumerate(ranked_full, start=1):
        shown = [] if ask_kind == "checklist" else show_pics.get(row.id, [])
        citations.append(
            {
                "id": row.id,
                "title": row.title or row.file_name,
                "score": round(score, 3),
                "images": [],
            }
        )
        title = row.title or row.file_name
        hopped = "\n（这一段是按前面资料里出现的名称再查到的）" if row.id in linked else ""
        block = f"【资料{index}】{title}{hopped}\n{snippet or snippet_of(search_q, row)}"
        grid = sheet_rows_for_ask(row.sheet_json or "", search_q)
        if grid:
            block += "\n" + grid
        notes = asset_notes_for_ask(note_pics.get(row.id, []))
        if notes:
            block += f"\n【图上的说明】\n{notes}"
        if ask_kind != "checklist" and shown:
            lines = []
            for item in shown[:4]:
                data = asset_dict(item)
                name = (item.alt_text or "图").strip()
                lines.append(f"![{name}]({data['url']})")
            block += "\n【可展示的图】\n" + "\n".join(lines)
        if use_notes:
            note = parse_wiki(row)
            if note.summary:
                flag = "（可能过期）" if note.stale else ""
                block += f"\n【笔记{flag}】{note.summary}"
        blocks.append(block)
    empty = {
        "answer": "当前范围内没找到相关资料。",
        "citations": [],
        "used_llm": False,
        "evidence_mode": mode,
        "wiki_update_hint": "",
        "used_vector": False,
        "ask_kind": ask_kind,
    }
    if not ranked:
        return {"early": empty, "question": question}, None
    if not llm_public().get("has_key"):
        return {
            "early": {
                "answer": "还没配 AI。先列出可能相关的资料，配好 Key 后再问可以写成回答。",
                "citations": citations,
                "used_llm": False,
                "evidence_mode": mode,
                "wiki_update_hint": "",
                "used_vector": used_vector,
                "ask_kind": ask_kind,
            },
            "question": question,
        }, None
    if ask_kind == "checklist":
        prompt = _checklist_style() + "\n\n" + "\n\n".join(blocks)
    else:
        prompt = (
            _ask_style(mode, policy["rule"])
            + "回答末尾用「依据：资料1、资料2」标出来源。只写本轮真正用到的（有原文支撑结论或冲突的），没用上、只是路过的不要写。\n\n"
            + "\n\n".join(blocks)
        )
    return {
        "early": None,
        "question": question,
        "messages": _ask_messages(question, prompt, history, ask_kind),
        "citations": citations,
        "ranked": ranked,
        "ranked_full": ranked_full,
        "note_pics": note_pics,
        "show_pics": show_pics,
        "mode": mode,
        "ask_kind": ask_kind,
        "used_vector": used_vector,
        "should_learn": ask_kind == "answer" and policy["wiki_enabled"] and policy["wiki_learn"] and bool(citations),
    }, None


_YIJU_RE = re.compile(r"依据[：:][^\n]*\s*$")
_UNUSED_HINT = re.compile(r"未提供|没有提供|未见|未提到|没用上|未写|未给出|未包含")


def _used_citation_indexes(citations: list, answer: str) -> set[int]:
    """回答正文里真正用到的资料序号。只说没见到的不算。"""

    if not citations or not (answer or "").strip():
        return set()
    body = _YIJU_RE.sub("", answer)
    used: set[int] = set()
    for match in re.finditer(r"资料\s*(\d+)", body):
        index = int(match.group(1))
        window = body[max(0, match.start() - 12) : match.end() + 20]
        if _UNUSED_HINT.search(window):
            continue
        used.add(index)
    if not used:
        for index, hit in enumerate(citations, start=1):
            title = (hit.get("title") or "").strip()
            if title and title in body:
                used.add(index)
    return {index for index in used if 1 <= index <= len(citations)}


def _keep_used_citations(citations: list, answer: str) -> tuple[list, str]:
    """出处和依据只留真正用到的资料。"""

    used = _used_citation_indexes(citations, answer)
    if not used:
        return citations, answer
    kept = [hit for index, hit in enumerate(citations, start=1) if index in used]
    labels = "、".join(f"资料{index}" for index in sorted(used))
    line = f"依据：{labels}"
    if _YIJU_RE.search(answer or ""):
        answer = _YIJU_RE.sub(line, (answer or "").rstrip())
    return kept, answer


def _finalize_llm_ask(prep: dict, answer: str) -> dict:
    citations, answer = _keep_used_citations(prep["citations"], answer)
    _fill_cited_images(citations, prep["ranked_full"], prep["note_pics"], prep["show_pics"], answer, prep["ask_kind"])
    hint = ""
    if prep["should_learn"]:
        hint = "摘要正在后台更新，不影响这次回答。"
        Thread(target=_learn_wikis_job, args=(prep["question"], [row.id for row, _score in prep["ranked"]]), daemon=True).start()
    return {
        "answer": answer,
        "citations": citations,
        "used_llm": True,
        "evidence_mode": prep["mode"],
        "wiki_update_hint": hint,
        "used_vector": prep["used_vector"],
        "ask_kind": prep["ask_kind"],
    }


def _stream_ask(prep: dict, library_id: int, session_id: int | None, request: Request, db):
    """检索完以后一边出字一边推给页面。"""

    if prep.get("early") is not None:
        if _client_stopped(request):
            return
        payload = _save_ask(db, library_id, session_id, prep["question"], prep["early"])
        yield _sse({"type": "done", "result": payload})
        return
    yield _sse(
        {
            "type": "start",
            "citations": [{"id": hit["id"], "title": hit["title"], "score": hit["score"], "images": []} for hit in prep["citations"]],
            "used_vector": prep["used_vector"],
            "ask_kind": prep["ask_kind"],
            "evidence_mode": prep["mode"],
        }
    )
    parts: list[str] = []
    try:
        for piece in chat_complete_stream(prep["messages"], timeout=ASK_ANSWER_TIMEOUT):
            if _client_stopped(request):
                return
            parts.append(piece)
            yield _sse({"type": "delta", "text": piece})
    except ValueError as exc:
        yield _sse({"type": "error", "message": str(exc)})
        return
    if _client_stopped(request):
        return
    answer = "".join(parts).strip()
    if not answer:
        try:
            answer = chat_complete(prep["messages"], timeout=ASK_ANSWER_TIMEOUT)
        except ValueError as exc:
            yield _sse({"type": "error", "message": str(exc)})
            return
        if _client_stopped(request):
            return
        yield _sse({"type": "delta", "text": answer})
    payload = _save_ask(db, library_id, session_id, prep["question"], _finalize_llm_ask(prep, answer))
    yield _sse({"type": "done", "result": payload})


@router.post("/kb/libraries/{library_id}/ask")
def ask_library(
    library_id: int,
    body: AskIn,
    request: Request,
    db: Session = Depends(get_db),
    stream: bool = Query(default=False),
):
    """当前库关键词加向量检索，再按原文回答并带出处。"""

    prep, err = _prepare_ask(library_id, body, db)
    if err is not None:
        return err
    if stream:
        return StreamingResponse(
            _stream_ask(prep, library_id, body.session_id, request, db),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    if prep.get("early") is not None:
        return _finish_ask(db, library_id, body.session_id, prep["question"], prep["early"])
    try:
        answer = chat_complete(prep["messages"], timeout=ASK_ANSWER_TIMEOUT)
    except ValueError as exc:
        return fail(str(exc))
    if _client_stopped(request):
        return fail("已停止")
    return _finish_ask(db, library_id, body.session_id, prep["question"], _finalize_llm_ask(prep, answer))


@router.get("/kb/documents/{doc_id}")
def get_document(doc_id: int, db: Session = Depends(get_db)):
    row = db.get(KbDocument, doc_id)
    if row is None:
        return fail("这份资料不存在", 404)
    data = _doc_dict(row, db)
    if db.dirty:
        db.commit()
    return ok(data)


@router.get("/kb/documents/{doc_id}/chunks")
def list_document_chunks(doc_id: int, db: Session = Depends(get_db)):
    """预览里看切片、改字。"""

    row = db.get(KbDocument, doc_id)
    if row is None:
        return fail("这份资料不存在", 404)
    _fill_search_text(row, db)
    index_document(db, row)
    items = ensure_chunks(db, row)
    db.commit()
    return ok({"items": [chunk_dict(item) for item in items]})


@router.put("/kb/chunks/{chunk_id}")
def update_document_chunk(chunk_id: int, body: ChunkPatch, db: Session = Depends(get_db)):
    """改一块切片，并重算这一块的向量。"""

    row = db.get(KbChunk, chunk_id)
    if row is None:
        return fail("这块切片不存在", 404)
    text = body.text.strip()
    if not text:
        return fail("请先写下切片内容")
    _, status = update_chunk_text(db, row, text, body.embed)
    if not body.embed:
        db.commit()
        db.refresh(row)
        return ok({**chunk_dict(row), "vector_ok": False, "vector_hint": "已保存这块。点「只处理向量」才算确认。"})
    db.commit()
    db.refresh(row)
    return ok({**chunk_dict(row), **vector_payload(status, chunk=True)})


@router.get("/kb/documents/{doc_id}/assets")
def list_document_assets(doc_id: int, db: Session = Depends(get_db)):
    """预览里看图、改识图文字。"""

    row = db.get(KbDocument, doc_id)
    if row is None:
        return fail("这份资料不存在", 404)
    _fill_assets(row, db, force=True)
    db.commit()
    return ok({"items": [asset_edit_dict(item) for item in list_doc_assets(db, row.id)]})


@router.post("/kb/documents/{doc_id}/vision")
def recognize_document(doc_id: int, db: Session = Depends(get_db)):
    """列表上点识图：认这份还没认过的图。"""

    row = db.get(KbDocument, doc_id)
    if row is None:
        return fail("这份资料不存在", 404)
    lib = _get_library(db, row.library_id)
    if lib is None:
        return fail("这个库不存在", 404)
    engine, err = _ready_vision(lib)
    if err is not None:
        return err
    _fill_assets(row, db)
    db.flush()
    if not list_doc_assets(db, row.id):
        return fail("这份资料没有可认的图")
    if pending_vision_count(db, row.id) == 0:
        return ok({"done": 0, "left": 0, "message": "这些图都认过了"})
    try:
        done = recognize_assets(db, row, 8, engine)
    except ValueError as exc:
        return fail(str(exc))
    rebuild_search_text(db, row)
    status = index_document(db, row, force=True)
    row.updated_at = datetime.utcnow()
    db.commit()
    left = pending_vision_count(db, row.id)
    message = f"已认 {done} 张"
    if left:
        message += f"，还有 {left} 张，再点一次识图"
    extra = vector_payload(status)
    message += "。" + extra["vector_hint"]
    return ok({"done": done, "left": left, "message": message, **extra})


@router.post("/kb/assets/{asset_id}/vision")
def recognize_asset(asset_id: int, db: Session = Depends(get_db)):
    """认一张图，认完立刻返回，方便进度一条条填。"""

    item = db.get(KbAsset, asset_id)
    if item is None:
        return fail("这张图不存在", 404)
    row = db.get(KbDocument, item.document_id)
    if row is None:
        return fail("这份资料不存在", 404)
    lib = _get_library(db, row.library_id)
    if lib is None:
        return fail("这个库不存在", 404)
    engine, err = _ready_vision(lib)
    if err is not None:
        return err
    try:
        recognize_one_asset(row, item, engine)
    except ValueError as exc:
        return fail(str(exc))
    rebuild_search_text(db, row)
    status = index_document(db, row, force=True)
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(item)
    return ok({**asset_edit_dict(item), **vector_payload(status)})


@router.put("/kb/documents/{doc_id}/assets")
def update_document_assets(doc_id: int, body: AssetBatchIn, db: Session = Depends(get_db)):
    """一次改多张图的说明，只存字，不重算向量。"""

    row = db.get(KbDocument, doc_id)
    if row is None:
        return fail("这份资料不存在", 404)
    if not body.items:
        return fail("没有要保存的图")
    ids = [item.id for item in body.items]
    found = {
        item.id: item
        for item in db.scalars(select(KbAsset).where(KbAsset.document_id == doc_id, KbAsset.id.in_(ids))).all()
    }
    for patch in body.items:
        item = found.get(patch.id)
        if item is None:
            continue
        text = pack_asset_note(patch.caption, patch.keywords, patch.ocr_text)
        item.ocr_text = text or OCR_SKIP
    rebuild_search_text(db, row)
    row.updated_at = datetime.utcnow()
    db.commit()
    return ok({"items": [asset_edit_dict(item) for item in list_doc_assets(db, row.id)], **vector_payload("pending")})


class CleanRuleIn(BaseModel):
    how: str = "contains"
    action: str = "replace"
    find: str = ""
    replace: str = ""


class FlowIn(BaseModel):
    step: str = ""
    parse: str = "standard"
    parse_hint: str = ""
    parse_script: str = ""
    cleans: list[str] = ["collapse"]
    rules: list[CleanRuleIn] = []
    script: str = ""
    chunk: str = "chars"
    vector: bool = True
    chunk_size: int = 400
    chunk_overlap: int = 60
    max_chunks: int = 40


@router.post("/kb/documents/{doc_id}/process")
def process_document(doc_id: int, body: FlowIn, db: Session = Depends(get_db)):
    """按预览里选的方式，只处理这一份资料。"""

    row = db.get(KbDocument, doc_id)
    if row is None:
        return fail("这份资料不存在", 404)
    runner = apply_document_all if body.step == "all" else apply_document_step
    status, quality = runner(db, row, body.model_dump())
    detail = ""
    for prefix in ("clean_failed:", "parse_failed:"):
        if status.startswith(prefix):
            detail = status[len(prefix) :]
    if body.step == "all" and (detail or status == "failed" or status.startswith("failed")):
        db.rollback()
        return fail(detail or _FLOW_HINTS.get(status) or "这一步没做成。")
    row.updated_at = datetime.utcnow()
    db.commit()
    extra = vector_payload("failed" if detail else status)
    if detail:
        extra["vector_hint"] = detail
    hint = _FLOW_HINTS.get(status)
    if hint:
        extra["vector_hint"] = hint
    return ok({**_doc_dict(row, db), **extra, **_flow_preview(row, db, status), "message": extra["vector_hint"], "quality": quality})


def _flow_preview(row: KbDocument, db: Session, status: str) -> dict:
    """把这一步做出来的字带回页面，方便看和改。"""

    data: dict = {}
    if status == "parsed":
        data["result_text"] = saved_parsed(row)
    elif status in {"cleaned", "done", "done_keywords"}:
        data["result_text"] = row.search_text or ""
    if status in {"chunked", "done", "done_keywords"}:
        data["chunks"] = [chunk_dict(item) for item in list_chunks(db, row.id)]
    return data


@router.put("/kb/documents/{doc_id}/stage")
def save_document_stage(doc_id: int, body: StageIn, db: Session = Depends(get_db)):
    """保存手改过的解析或清洗结果。不自动做下一步。"""

    row = db.get(KbDocument, doc_id)
    if row is None:
        return fail("这份资料不存在", 404)
    text = body.text.strip()
    if not text:
        return fail("请先留下要保存的字")
    if body.step == "parse":
        remember_parsed(row, text)
    elif body.step == "clean":
        row.search_text = text
    else:
        return fail("这一步不能这样存")
    row.updated_at = datetime.utcnow()
    db.commit()
    saved = saved_parsed(row) if body.step == "parse" else row.search_text or ""
    return ok({**_doc_dict(row, db), "result_text": saved, "message": "已保存修改。下一步会用这段字。"})


@router.post("/kb/documents/{doc_id}/vector")
def rebuild_document_vector(doc_id: int, db: Session = Depends(get_db)):
    """按当前正文和图说明，整份重算一次向量。改完图说明后点一次即可。"""

    row = db.get(KbDocument, doc_id)
    if row is None:
        return fail("这份资料不存在", 404)
    _fill_search_text(row, db, force=True)
    rebuild_search_text(db, row)
    status = index_document(db, row, force=True)
    row.updated_at = datetime.utcnow()
    db.commit()
    extra = vector_payload(status)
    if status == "updated":
        extra["vector_hint"] = "这份资料的向量已重算。"
        if extra.get("milvus_hint"):
            extra["vector_hint"] += " " + extra["milvus_hint"]
    return ok({**_doc_dict(row, db), **extra})


@router.put("/kb/assets/{asset_id}")
def update_asset(asset_id: int, body: AssetPatch, db: Session = Depends(get_db)):
    """人工改正识图文字，只存字，不重算向量。"""

    item = db.get(KbAsset, asset_id)
    if item is None:
        return fail("这张图不存在", 404)
    row = db.get(KbDocument, item.document_id)
    if row is None:
        return fail("这份资料不存在", 404)
    text = pack_asset_note(body.caption, body.keywords, body.ocr_text)
    item.ocr_text = text or OCR_SKIP
    rebuild_search_text(db, row)
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(item)
    return ok({**asset_edit_dict(item), **vector_payload("pending")})


def _save_wiki(row: KbDocument, summary: str, db: Session):
    text = clip_summary(summary)
    if not text:
        return fail("摘要是空的")
    row.wiki_json = dump_wiki(text, row.file_hash or "")
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return ok(_doc_dict(row, db))


@router.post("/kb/documents/{doc_id}/wiki")
def generate_wiki(doc_id: int, db: Session = Depends(get_db)):
    """开了 Wiki 才能写。点了才生成，上传不自动写。"""

    row = db.get(KbDocument, doc_id)
    if row is None:
        return fail("这份资料不存在", 404)
    lib = _get_library(db, row.library_id)
    if lib is None:
        return fail("这个库不存在", 404)
    if not parse_policy(lib)["wiki_enabled"]:
        return fail("这个库还没开启 Wiki")
    if not llm_public().get("has_key"):
        return fail("请先在设置里填写 AI Key")
    _fill_search_text(row, db)
    db.commit()
    body = (row.search_text or "").strip()
    if not body:
        return fail("抽不出正文，没法写摘要")
    try:
        text = chat_complete(
            [
                {"role": "system", "content": "你根据资料写短摘要，只写原文里有的内容。"},
                {
                    "role": "user",
                    "content": f"用大约250字说明这份资料是什么、关键看哪。不要编造。\n\n标题：{row.title or row.file_name}\n\n{body[:6000]}",
                },
            ]
        )
    except ValueError as exc:
        return fail(str(exc))
    return _save_wiki(row, text, db)


@router.put("/kb/documents/{doc_id}/wiki")
def save_wiki(doc_id: int, body: WikiIn, db: Session = Depends(get_db)):
    row = db.get(KbDocument, doc_id)
    if row is None:
        return fail("这份资料不存在", 404)
    lib = _get_library(db, row.library_id)
    if lib is None:
        return fail("这个库不存在", 404)
    if not parse_policy(lib)["wiki_enabled"]:
        return fail("这个库还没开启 Wiki")
    return _save_wiki(row, body.summary, db)


@router.delete("/kb/documents/{doc_id}/wiki")
def clear_wiki(doc_id: int, db: Session = Depends(get_db)):
    """删摘要。关着 Wiki 也能清掉旧的。"""

    row = db.get(KbDocument, doc_id)
    if row is None:
        return fail("这份资料不存在", 404)
    row.wiki_json = ""
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return ok(_doc_dict(row, db))


@router.put("/kb/documents/{doc_id}")
def update_document(doc_id: int, body: DocumentPatch, db: Session = Depends(get_db)):
    row = db.get(KbDocument, doc_id)
    if row is None:
        return fail("这份资料不存在", 404)
    if body.title is not None:
        title = body.title.strip()
        if not title:
            return fail("请填写名称")
        row.title = title
    if body.tags is not None:
        row.tags = body.tags.strip()
    if "folder_id" in body.model_fields_set:
        if not _folder_in_library(db, row.library_id, body.folder_id):
            return fail("文件夹不在这个库里")
        row.folder_id = body.folder_id
    if "disabled" in body.model_fields_set and body.disabled is not None:
        row.disabled = 1 if body.disabled else 0
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return ok(_doc_dict(row, db))


@router.delete("/kb/documents/{doc_id}")
def delete_document(doc_id: int, db: Session = Depends(get_db)):
    row = db.get(KbDocument, doc_id)
    if row is None:
        return fail("这份资料不存在", 404)
    library_id = row.library_id
    rel_path = row.rel_path
    clear_assets(db, row)
    clear_chunks(db, row.id)
    db.delete(row)
    db.commit()
    remove_file(library_id, rel_path)
    return ok(True)


@router.get("/kb/documents/{doc_id}/file")
def download_document(doc_id: int, db: Session = Depends(get_db)):
    row = db.get(KbDocument, doc_id)
    if row is None:
        return fail("这份资料不存在", 404)
    try:
        path = abs_path(row.library_id, row.rel_path)
    except ValueError:
        return fail("文件路径无效", 404)
    if not path.is_file():
        return fail("原件找不到了", 404)
    media = "application/octet-stream"
    if row.kind == "pdf":
        media = "application/pdf"
    elif row.kind == "image":
        media = "image/*"
    elif row.kind == "text":
        media = "text/plain; charset=utf-8"
    filename = quote(row.file_name or path.name)
    return FileResponse(path, media_type=media, filename=row.file_name, headers={"Content-Disposition": f"inline; filename*=UTF-8''{filename}"})


@router.get("/kb/documents/{doc_id}/images.pdf")
def download_images_pdf(doc_id: int, db: Session = Depends(get_db)):
    """把这份资料抽出的图按顺序合成一个 PDF。"""

    row = db.get(KbDocument, doc_id)
    if row is None:
        return fail("这份资料不存在", 404)
    blob = document_images_pdf(db, row)
    if not blob:
        return fail("这份没有可合并的图")
    stem = (row.file_name or "图片").rsplit(".", 1)[0]
    filename = quote(f"{stem}-图.pdf")
    return Response(
        content=blob,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{filename}"},
    )


@router.get("/kb/assets/{asset_id}/file")
def download_asset(asset_id: int, db: Session = Depends(get_db)):
    """出处里的抽出图。独立图片走原件路径。"""

    row = db.get(KbAsset, asset_id)
    if row is None:
        return fail("这张图不存在", 404)
    try:
        path = abs_path(row.library_id, row.rel_path)
    except ValueError:
        return fail("图片路径无效", 404)
    if not path.is_file():
        return fail("图片找不到了", 404)
    suffix = path.suffix.lower()
    media = {
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }.get(suffix, "image/jpeg")
    filename = quote(path.name)
    return FileResponse(path, media_type=media, filename=path.name, headers={"Content-Disposition": f"inline; filename*=UTF-8''{filename}"})


@router.get("/kb/documents/{doc_id}/text")
def read_document_text(doc_id: int, db: Session = Depends(get_db)):
    """预览正文。表格走抽字，不要把 xlsx 压缩包当文本读。"""

    row = db.get(KbDocument, doc_id)
    if row is None:
        return fail("这份资料不存在", 404)
    if row.kind != "text":
        return fail("这份不是文本，请用预览打开")
    try:
        path = abs_path(row.library_id, row.rel_path)
        data = path.read_bytes()
    except (ValueError, OSError):
        return fail("读不了这份文本", 404)
    text = extract_search_text(row.file_name, data, collapse=False)
    if is_sheet_name(row.file_name):
        _fill_search_text(row, db)
        index_document(db, row)
        if db.dirty:
            db.commit()
    if not text.strip():
        return fail("这份表格抽不出字")
    return ok({"text": text})
