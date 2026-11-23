"""对某一份资料按选定方式重做解析、清洗、切片和向量。只在点了按钮时调用。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.kb.assets import list_doc_assets, ocr_for_search
from app.kb.chunk import split_chunks, split_paragraphs, split_whole
from app.kb.clean import clean_choice
from app.kb.extract import extract_search_text, extract_sheet_grid, is_sheet_name
from app.kb.models import KbDocument
from app.kb.pipeline import normalize_flow, remember_flow
from app.kb.store import abs_path
from app.kb.vector import has_edited_chunks, replace_chunk_texts

# 只抽开头时用更短的上限。标准抽出仍是原来的 20000 / 40000 / 500。
_HEAD_TEXT = 4000
_HEAD_SHEET = 8000
_HEAD_ROWS = 80


def apply_document_flow(db: Session, row: KbDocument, raw: dict) -> str:
    """按这份表单重做这一份。手改过的切片不覆盖。"""

    if has_edited_chunks(db, row.id):
        return "skipped_edited"
    flow = normalize_flow(raw)
    try:
        data = abs_path(row.library_id, row.rel_path).read_bytes()
    except (ValueError, OSError):
        return "failed"
    text_limit, sheet_limit, sheet_rows = _limits(flow["parse"])
    raw_text = extract_search_text(
        row.file_name,
        data,
        collapse=False,
        text_limit=text_limit,
        sheet_limit=sheet_limit,
        sheet_rows=sheet_rows,
    )
    limit = sheet_limit if is_sheet_name(row.file_name) else text_limit
    body = clean_choice(raw_text, flow["clean"], limit)
    notes = _notes(db, row)
    parts = [body, *notes]
    text = " ".join(part for part in parts if part).strip()[:limit]
    if not text:
        return "failed"
    row.search_text = text
    if is_sheet_name(row.file_name):
        grid = extract_sheet_grid(row.file_name, data, sheet_rows)
        if grid:
            row.sheet_json = grid
    remember_flow(row, flow)
    source = f"{row.title or ''} {row.tags or ''} {text}".strip()
    chunks = _cut(source, flow, limit)
    if not chunks:
        return "failed"
    return replace_chunk_texts(db, row, chunks, bool(flow["vector"]))


def _limits(parse: str) -> tuple[int, int, int]:
    if parse == "head":
        return _HEAD_TEXT, _HEAD_SHEET, _HEAD_ROWS
    return 20000, 40000, 500


def _notes(db: Session, row: KbDocument) -> list[str]:
    """图名和识图文字仍留在检索正文里。"""

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
