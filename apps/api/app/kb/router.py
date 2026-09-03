"""知识库接口：多库、文件夹、上传、预览、提问。"""

from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ai import chat_complete, llm_public
from app.core.response import fail, ok
from app.db.session import get_db
from app.kb.extract import extract_search_text
from app.kb.models import KbDocument, KbFolder, KbLibrary
from app.kb.search import folder_scope, rank_documents, snippet_of
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


class FolderIn(BaseModel):
    name: str = Field(default="", max_length=200)
    parent_id: int | None = None


class DocumentPatch(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    tags: str | None = Field(default=None, max_length=500)
    folder_id: int | None = None


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    folder_id: int | None = None
    only_folder: bool = False


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value else ""


def _library_dict(row: KbLibrary) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description or "",
        "created_at": _iso(row.created_at),
    }


def _folder_dict(row: KbFolder) -> dict:
    return {
        "id": row.id,
        "library_id": row.library_id,
        "parent_id": row.parent_id,
        "name": row.name,
    }


def _doc_dict(row: KbDocument) -> dict:
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


@router.delete("/kb/libraries/{library_id}")
def delete_library(library_id: int, db: Session = Depends(get_db)):
    row = _get_library(db, library_id)
    if row is None:
        return fail("这个库不存在", 404)
    db.execute(KbDocument.__table__.delete().where(KbDocument.library_id == library_id))
    db.execute(KbFolder.__table__.delete().where(KbFolder.library_id == library_id))
    db.delete(row)
    db.commit()
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
        items.append(_doc_dict(row))
    return ok({"items": items})


@router.post("/kb/libraries/{library_id}/documents")
async def upload_document(
    library_id: int,
    file: UploadFile = File(...),
    folder_id: int | None = Form(default=None),
    tags: str = Form(default=""),
    force: bool = Form(default=False),
    db: Session = Depends(get_db),
):
    if _get_library(db, library_id) is None:
        return fail("这个库不存在", 404)
    if not _folder_in_library(db, library_id, folder_id):
        return fail("文件夹不在这个库里")
    data = await file.read()
    if not data:
        return fail("文件是空的")
    digest = file_digest(data)
    existing = db.scalar(
        select(KbDocument).where(KbDocument.library_id == library_id, KbDocument.file_hash == digest)
    )
    if existing and not force:
        return fail(f"库里已有相同文件「{existing.title or existing.file_name}」，确认后可另存")
    file_name = safe_filename(file.filename or "未命名")
    kind = kind_of(file_name)
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
        search_text=extract_search_text(file_name, data),
        updated_at=datetime.utcnow(),
    )
    db.add(row)
    db.flush()
    rel_path = f"{row.id}_{file_name}"
    write_bytes(library_id, rel_path, data)
    row.rel_path = rel_path
    db.commit()
    db.refresh(row)
    return ok(_doc_dict(row))


def _fill_search_text(row: KbDocument) -> None:
    """旧文件还没抽过正文时，提问前补一次。"""

    if (row.search_text or "").strip():
        return
    try:
        path = abs_path(row.library_id, row.rel_path)
        data = path.read_bytes()
    except (ValueError, OSError):
        return
    row.search_text = extract_search_text(row.file_name, data)


@router.post("/kb/libraries/{library_id}/ask")
def ask_library(library_id: int, body: AskIn, db: Session = Depends(get_db)):
    """当前库关键词检索，再按原文回答并带出处。"""

    if _get_library(db, library_id) is None:
        return fail("这个库不存在", 404)
    if body.only_folder and body.folder_id is not None and not _folder_in_library(db, library_id, body.folder_id):
        return fail("文件夹不在这个库里")
    question = body.question.strip()
    if not question:
        return fail("请先写问题")
    folders = db.scalars(select(KbFolder).where(KbFolder.library_id == library_id)).all()
    scope = folder_scope(list(folders), body.folder_id) if body.only_folder else None
    stmt = select(KbDocument).where(KbDocument.library_id == library_id)
    rows = list(db.scalars(stmt).all())
    if scope is not None:
        rows = [row for row in rows if row.folder_id in scope]
    for row in rows:
        _fill_search_text(row)
    db.commit()
    ranked = rank_documents(question, rows)
    citations = []
    blocks = []
    for index, (row, score) in enumerate(ranked, start=1):
        snippet = snippet_of(question, row)
        citations.append(
            {
                "id": row.id,
                "title": row.title or row.file_name,
                "score": round(score, 3),
            }
        )
        blocks.append(f"【资料{index}】{row.title or row.file_name}\n{snippet}")
    if not ranked:
        return ok({"answer": "当前范围内没找到相关资料。", "citations": [], "used_llm": False})
    if not llm_public().get("has_key"):
        return ok(
            {
                "answer": "还没配 AI。先列出可能相关的资料，配好 Key 后再问可以写成回答。",
                "citations": citations,
                "used_llm": False,
            }
        )
    prompt = (
        "只根据下面资料回答。没有依据就说资料里没有。不要编造。"
        "回答末尾用「依据：资料1、资料2」标出来源。\n\n"
        + "\n\n".join(blocks)
    )
    try:
        answer = chat_complete(
            [
                {"role": "system", "content": "你是知识库助手，依据用户资料作答，并标明出处。"},
                {"role": "user", "content": f"问题：{question}\n\n{prompt}"},
            ]
        )
    except ValueError as exc:
        return fail(str(exc))
    return ok({"answer": answer, "citations": citations, "used_llm": True})


@router.get("/kb/documents/{doc_id}")
def get_document(doc_id: int, db: Session = Depends(get_db)):
    row = db.get(KbDocument, doc_id)
    if row is None:
        return fail("这份资料不存在", 404)
    return ok(_doc_dict(row))


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
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return ok(_doc_dict(row))


@router.delete("/kb/documents/{doc_id}")
def delete_document(doc_id: int, db: Session = Depends(get_db)):
    row = db.get(KbDocument, doc_id)
    if row is None:
        return fail("这份资料不存在", 404)
    library_id = row.library_id
    rel_path = row.rel_path
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


@router.get("/kb/documents/{doc_id}/text")
def read_document_text(doc_id: int, db: Session = Depends(get_db)):
    row = db.get(KbDocument, doc_id)
    if row is None:
        return fail("这份资料不存在", 404)
    if row.kind != "text":
        return fail("这份不是文本，请用预览打开")
    try:
        path = abs_path(row.library_id, row.rel_path)
        text = path.read_text(encoding="utf-8", errors="ignore")
    except (ValueError, OSError):
        return fail("读不了这份文本", 404)
    return ok({"text": text})
