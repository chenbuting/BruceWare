"""对某一份资料只做打开的那一个模块。解析、清洗、切片、向量互不连带。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.kb.assets import list_doc_assets, ocr_for_search
from app.kb.chunk import split_chunks, split_paragraphs, split_whole
from app.kb.clean import CleanScriptError, clean_document
from app.kb.extract import extract_search_text, extract_sheet_grid, is_sheet_name
from app.kb.models import KbDocument
from app.kb.milvus_store import delete_document_vectors
from app.kb.pipeline import normalize_flow, remember_flow, remember_parsed, stored_flow
from app.kb.store import abs_path
from app.kb.vector import embed_current_chunks, has_edited_chunks, list_chunks, replace_chunk_texts

_HEAD_TEXT = 4000
_HEAD_SHEET = 8000
_HEAD_ROWS = 80
_STEPS = {"parse", "clean", "chunk", "vector"}


def apply_document_step(db: Session, row: KbDocument, raw: dict) -> tuple[str, list[dict]]:
    """只做 raw 里的 step。清洗会带上每一类过了几条、挡了几条。"""

    step = str(raw.get("step") or "")
    if step not in _STEPS:
        return "failed", []
    current = stored_flow(row) or normalize_flow(None)
    chosen = normalize_flow({**current, **raw})
    quality: list[dict] = []
    if step == "parse":
        status = _parse(db, row, chosen)
    elif step == "clean":
        status, quality = _clean(db, row, chosen)
    elif step == "chunk":
        status = _chunk(db, row, chosen)
    else:
        status = _vector(db, row, chosen)
    if status != "failed":
        remember_flow(row, chosen)
    return status, quality


def _parse(db: Session, row: KbDocument, flow: dict) -> str:
    raw_text, _limit, _rows, data = _read_raw(row, flow)
    if data is None:
        return "failed"
    if not raw_text.strip():
        return "failed"
    remember_parsed(row, raw_text)
    if is_sheet_name(row.file_name):
        grid = extract_sheet_grid(row.file_name, data, _rows)
        if grid:
            row.sheet_json = grid
    return "parsed"


def _clean(db: Session, row: KbDocument, flow: dict) -> tuple[str, list[dict]]:
    saved = _saved_parsed(row)
    limit = _limits(flow["parse"])[1 if is_sheet_name(row.file_name) else 0]
    if saved.strip():
        raw_text = saved
    else:
        raw_text, limit, _rows, data = _read_raw(row, flow)
        if data is None and not raw_text.strip():
            return "failed", []
    try:
        body, quality = clean_document(raw_text, flow["cleans"], flow["rules"], limit, flow.get("script") or "")
    except CleanScriptError as exc:
        return f"clean_failed:{exc}", []
    notes = _notes(db, row)
    text = " ".join(part for part in [body, *notes] if part).strip()[:limit]
    if not text:
        return "failed", []
    row.search_text = text
    return "cleaned", quality


def _chunk(db: Session, row: KbDocument, flow: dict) -> str:
    if has_edited_chunks(db, row.id):
        return "skipped_edited"
    text = (row.search_text or "").strip()
    if not text:
        return "failed:还没有可切的正文"
    limit = _limits(flow["parse"])[1 if is_sheet_name(row.file_name) else 0]
    source = f"{row.title or ''} {row.tags or ''} {text}".strip()
    parts = _cut(source, flow, limit)
    if not parts:
        return "failed"
    replace_chunk_texts(db, row, parts, False)
    return "chunked"


def _vector(db: Session, row: KbDocument, flow: dict) -> str:
    chunks = list_chunks(db, row.id)
    if not chunks:
        return "failed:还没有切片"
    if not flow["vector"]:
        for item in chunks:
            item.embedding = ""
            item.profile = ""
        row.embedding_profile = ""
        row.vector_stamp = ""
        delete_document_vectors(row.id)
        return "skipped"
    return embed_current_chunks(db, row)


def _read_raw(row: KbDocument, flow: dict) -> tuple[str, int, int, bytes | None]:
    """抽出还没清洗的字。读不了文件时，用上次解析留下的字。"""

    text_limit, sheet_limit, sheet_rows = _limits(flow["parse"])
    limit = sheet_limit if is_sheet_name(row.file_name) else text_limit
    try:
        data = abs_path(row.library_id, row.rel_path).read_bytes()
    except (ValueError, OSError):
        saved = _saved_parsed(row)
        return saved, limit, sheet_rows, None
    raw_text = extract_search_text(
        row.file_name,
        data,
        collapse=False,
        text_limit=text_limit,
        sheet_limit=sheet_limit,
        sheet_rows=sheet_rows,
    )
    return raw_text, limit, sheet_rows, data


def _saved_parsed(row: KbDocument) -> str:
    import json

    raw = (row.extra or "").strip()
    if not raw:
        return ""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return ""
    if not isinstance(data, dict):
        return ""
    return str(data.get("parsed_text") or "")


def _limits(parse: str) -> tuple[int, int, int]:
    if parse == "head":
        return _HEAD_TEXT, _HEAD_SHEET, _HEAD_ROWS
    return 20000, 40000, 500


def _notes(db: Session, row: KbDocument) -> list[str]:
    notes: list[str] = []
    for item in list_doc_assets(db, row.id):
        if item.alt_text:
            notes.append(item.alt_text)
        extra = ocr_for_search(item.ocr_text or "")
        if extra:
            notes.append(extra)
    return notes


def _cut(text: str, flow: dict, limit: int) -> list[str]:
    kind = flow["chunk"]
    if kind == "paragraph":
        return split_paragraphs(text, flow["max_chunks"])
    if kind == "whole":
        return split_whole(text, limit)
    return split_chunks(
        text,
        size=flow["chunk_size"],
        overlap=flow["chunk_overlap"],
        limit=flow["max_chunks"],
        collapse=False,
    )
