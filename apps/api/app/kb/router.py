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
from app.kb.assets import (
    OCR_SKIP,
    already_extracted,
    append_asset_alts,
    asset_dict,
    asset_edit_dict,
    asset_notes_for_ask,
    assets_for_docs,
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
from app.kb.search import folder_scope, snippet_of
from app.kb.vector import clear_chunks, hybrid_rank, index_document, score_chunks, supplement_hits
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


class WikiIn(BaseModel):
    summary: str = Field(default="", max_length=800)


class AssetPatch(BaseModel):
    caption: str = Field(default="", max_length=200)
    keywords: str = Field(default="", max_length=200)
    ocr_text: str = Field(default="", max_length=1500)


class FolderIn(BaseModel):
    name: str = Field(default="", max_length=200)
    parent_id: int | None = None


class DocumentPatch(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    tags: str | None = Field(default=None, max_length=500)
    folder_id: int | None = None


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
    note = parse_wiki(row)
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
        body.wiki_enabled, mode, body.rule, body.wiki_learn, body.vision_enabled, body.vision_engine
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
    lib = _get_library(db, library_id)
    if lib is None:
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
    alts = save_extracted_images(db, row, data)
    append_asset_alts(row, alts)
    index_document(db, row)
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


def _learn_wikis(question: str, ranked: list, db: Session) -> str:
    """按这次出处更新摘要。没出处不提示；一次最多 5 份。"""

    if not ranked:
        return ""
    truncated = len(ranked) > ASK_WIKI_LIMIT
    titles: list[str] = []
    for row, _score in ranked[:ASK_WIKI_LIMIT]:
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
    return learn_hint(len(ranked), titles, truncated)


def _ask_style(mode: str, rule: str) -> str:
    """拼给模型的回答约束。"""

    if mode == "loose":
        text = "可以参考摘要帮助概括，但必须标明来自哪份资料。图上认下来的图意和字也算出处。吃不准就回到原文，不要编造。"
    else:
        text = "必须依据原文片段和图上认下来的图意、文字作答，不能把摘要当证据。可以说见哪张图。没有这些依据就说资料里没有。"
    extra = (rule or "").strip()
    if extra:
        text += f" 额外规则：{extra}"
    text += (
        " 用 Markdown 排版：对比用表格，条目用列表。"
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


def _ask_messages(question: str, prompt: str, history: list[AskTurnIn]) -> list[dict]:
    """历史只帮听懂指代，证据仍是本轮资料。"""

    messages = [
        {
            "role": "system",
            "content": (
                "你是知识库助手，依据本轮资料原文和图上的说明作答，并标明出处。"
                "用户可能接着上一句问。刚才的对话只用来听懂「那」「刚才」「这份」指什么。"
                "编号、日期、金额、开户行、证书名称等事实必须依据本轮资料，不能拿上一轮回答当证据。"
                "本轮资料没有就说资料里没有。"
            ),
        }
    ]
    for turn in history:
        messages.append({"role": "user", "content": turn.question})
        messages.append({"role": "assistant", "content": turn.answer})
    messages.append({"role": "user", "content": f"问题：{question}\n\n{prompt}"})
    return messages


def _finish_ask(db, library_id: int, session_id: int | None, question: str, payload: dict):
    """回答成功后写入当前会话，失败的提问不建空会话。"""

    session = ensure_session(db, library_id, session_id, question)
    save_turn(db, session, question, payload)
    payload["session_id"] = session.id
    return ok(payload)


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


@router.post("/kb/libraries/{library_id}/ask")
def ask_library(library_id: int, body: AskIn, db: Session = Depends(get_db)):
    """当前库关键词加向量检索，再按原文回答并带出处。"""

    lib = _get_library(db, library_id)
    if lib is None:
        return fail("这个库不存在", 404)
    if body.only_folder and body.folder_id is not None and not _folder_in_library(db, library_id, body.folder_id):
        return fail("文件夹不在这个库里")
    question = body.question.strip()
    if not question:
        return fail("请先写问题")
    history = _ask_history(body.history)
    search_q = _search_question(question, history)
    policy = parse_policy(lib)
    mode = resolve_mode(policy["evidence_mode"], body.evidence_mode)
    folders = db.scalars(select(KbFolder).where(KbFolder.library_id == library_id)).all()
    scope = folder_scope(list(folders), body.folder_id) if body.only_folder else None
    stmt = select(KbDocument).where(KbDocument.library_id == library_id)
    rows = list(db.scalars(stmt).all())
    if scope is not None:
        rows = [row for row in rows if row.folder_id in scope]
    for row in rows:
        _fill_search_text(row)
        _fill_assets(row, db)
        index_document(db, row)
    db.commit()
    chunk_best = score_chunks(db, library_id, search_q, {row.id for row in rows})
    ranked_full = supplement_hits(search_q, rows, hybrid_rank(search_q, rows, chunk_best), chunk_best)
    ranked = [(row, score) for row, score, _snippet in ranked_full]
    used_vector = bool(chunk_best)
    citations = []
    blocks = []
    use_notes = policy["wiki_enabled"] and mode == "loose"
    pictures = assets_for_docs(db, [row.id for row, _score, _snip in ranked_full], search_q)
    for index, (row, score, snippet) in enumerate(ranked_full, start=1):
        citations.append(
            {
                "id": row.id,
                "title": row.title or row.file_name,
                "score": round(score, 3),
                "images": [asset_dict(item) for item in pictures.get(row.id, [])],
            }
        )
        block = f"【资料{index}】{row.title or row.file_name}\n{snippet or snippet_of(search_q, row)}"
        notes = asset_notes_for_ask(pictures.get(row.id, []))
        if notes:
            block += f"\n【图上的说明】\n{notes}"
        shown = pictures.get(row.id, [])
        if shown:
            lines = []
            for item in shown:
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
    }
    if not ranked:
        return _finish_ask(db, library_id, body.session_id, question, empty)
    if not llm_public().get("has_key"):
        return _finish_ask(
            db,
            library_id,
            body.session_id,
            question,
            {
                "answer": "还没配 AI。先列出可能相关的资料，配好 Key 后再问可以写成回答。",
                "citations": citations,
                "used_llm": False,
                "evidence_mode": mode,
                "wiki_update_hint": "",
                "used_vector": used_vector,
            },
        )
    prompt = (
        _ask_style(mode, policy["rule"])
        + "回答末尾用「依据：资料1、资料2」标出来源。\n\n"
        + "\n\n".join(blocks)
    )
    try:
        answer = chat_complete(_ask_messages(question, prompt, history), timeout=ASK_ANSWER_TIMEOUT)
    except ValueError as exc:
        return fail(str(exc))
    hint = ""
    if policy["wiki_enabled"] and policy["wiki_learn"] and citations:
        hint = _learn_wikis(question, ranked, db)
    return _finish_ask(
        db,
        library_id,
        body.session_id,
        question,
        {
            "answer": answer,
            "citations": citations,
            "used_llm": True,
            "evidence_mode": mode,
            "wiki_update_hint": hint,
            "used_vector": used_vector,
        },
    )


@router.get("/kb/documents/{doc_id}")
def get_document(doc_id: int, db: Session = Depends(get_db)):
    row = db.get(KbDocument, doc_id)
    if row is None:
        return fail("这份资料不存在", 404)
    return ok(_doc_dict(row))


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
    index_document(db, row)
    row.updated_at = datetime.utcnow()
    db.commit()
    left = pending_vision_count(db, row.id)
    message = f"已认 {done} 张"
    if left:
        message += f"，还有 {left} 张，再点一次识图"
    return ok({"done": done, "left": left, "message": message})


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
    index_document(db, row)
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(item)
    return ok(asset_edit_dict(item))


@router.put("/kb/assets/{asset_id}")
def update_asset(asset_id: int, body: AssetPatch, db: Session = Depends(get_db)):
    """人工改正识图文字，并重拼检索。"""

    item = db.get(KbAsset, asset_id)
    if item is None:
        return fail("这张图不存在", 404)
    row = db.get(KbDocument, item.document_id)
    if row is None:
        return fail("这份资料不存在", 404)
    text = pack_asset_note(body.caption, body.keywords, body.ocr_text)
    item.ocr_text = text or OCR_SKIP
    rebuild_search_text(db, row)
    index_document(db, row)
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(item)
    return ok(asset_edit_dict(item))


def _save_wiki(row: KbDocument, summary: str, db: Session):
    text = clip_summary(summary)
    if not text:
        return fail("摘要是空的")
    row.wiki_json = dump_wiki(text, row.file_hash or "")
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return ok(_doc_dict(row))


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
    _fill_search_text(row)
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
