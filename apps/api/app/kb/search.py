"""知识库关键词检索：文件名、标签、抽出的正文。"""

from __future__ import annotations

import re

from app.kb.models import KbDocument, KbFolder


def search_terms(question: str) -> list[str]:
    """问句拆成检索词：连续中文、英文数字。"""

    cleaned = question.strip().lower()
    if not cleaned:
        return []
    terms = set(re.findall(r"[a-z0-9_]{2,}|[\u4e00-\u9fff]{2,}", cleaned))
    for segment in re.findall(r"[\u4e00-\u9fff]{3,}", cleaned):
        for index in range(len(segment) - 1):
            terms.add(segment[index : index + 2])
    return [term for term in terms if len(term) >= 2][:24]


def folder_scope(folders: list[KbFolder], folder_id: int | None) -> set[int] | None:
    """当前文件夹及其下级。None 表示整库。"""

    if folder_id is None:
        return None
    ids = {folder_id}
    changed = True
    while changed:
        changed = False
        for row in folders:
            if row.parent_id in ids and row.id not in ids:
                ids.add(row.id)
                changed = True
    return ids


def _haystack(row: KbDocument) -> str:
    return f"{row.title}\n{row.file_name}\n{row.tags}\n{row.search_text or ''}".lower()


def score_document(question: str, row: KbDocument) -> float:
    """相关分 0~1。"""

    q = question.strip().lower()
    blob = _haystack(row)
    if not q or not blob:
        return 0.0
    if q in blob:
        return 1.0
    terms = search_terms(question)
    if not terms:
        return 0.0
    hit = sum(1 for term in terms if term in blob)
    if not hit:
        return 0.0
    name = f"{row.title} {row.file_name} {row.tags}".lower()
    name_hit = sum(1 for term in terms if term in name)
    return min(1.0, hit / len(terms) + name_hit * 0.15)


def snippet_of(question: str, row: KbDocument, limit: int = 900) -> str:
    """截一段靠近问句的正文。"""

    body = (row.search_text or "").strip()
    if not body:
        return (row.title or row.file_name or "")[:limit]
    terms = search_terms(question)
    lower = body.lower()
    pos = -1
    for term in terms:
        pos = lower.find(term)
        if pos >= 0:
            break
    if pos < 0:
        return body[:limit]
    start = max(0, pos - 80)
    return body[start : start + limit]


def rank_documents(question: str, rows: list[KbDocument], top_k: int = 6) -> list[tuple[KbDocument, float]]:
    scored = [(row, score_document(question, row)) for row in rows]
    scored = [item for item in scored if item[1] > 0]
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:top_k]
