"""知识库文本向量：切段、入库、和关键词一起打分。"""

from __future__ import annotations

import json
import math

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ai import embed_texts, embedding_profile, llm_public
from app.kb.models import KbChunk, KbDocument
from app.kb.search import _haystack, expand_snippet, score_document, snippet_of, uncovered_terms

_CHUNK_SIZE = 400
_CHUNK_OVERLAP = 60
_MAX_CHUNKS = 40
_VEC_FLOOR = 0.28


def split_chunks(text: str) -> list[str]:
    """按字数切段，相邻留一点重叠。"""

    body = " ".join((text or "").split())
    if not body:
        return []
    if len(body) <= _CHUNK_SIZE:
        return [body]
    parts: list[str] = []
    start = 0
    while start < len(body) and len(parts) < _MAX_CHUNKS:
        parts.append(body[start : start + _CHUNK_SIZE])
        start += _CHUNK_SIZE - _CHUNK_OVERLAP
    return parts


def _parse_vec(raw: str) -> list[float]:
    try:
        data = json.loads(raw or "")
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [float(item) for item in data]


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / (na * nb)


def clear_chunks(db: Session, document_id: int) -> None:
    db.execute(KbChunk.__table__.delete().where(KbChunk.document_id == document_id))


def index_document(db: Session, row: KbDocument) -> bool:
    """抽出正文后写入向量。失败返回 False，提问仍走关键词。"""

    if not llm_public().get("has_key"):
        return False
    profile = embedding_profile()
    if (row.embedding_profile or "") == profile:
        exists = db.scalar(select(KbChunk.id).where(KbChunk.document_id == row.id).limit(1))
        if exists:
            return True
    body = (row.search_text or "").strip()
    if not body:
        return False
    parts = split_chunks(f"{row.title or ''} {row.tags or ''} {body}")
    if not parts:
        return False
    try:
        vectors = embed_texts(parts)
    except ValueError:
        return False
    if len(vectors) != len(parts):
        return False
    clear_chunks(db, row.id)
    for index, (text, vec) in enumerate(zip(parts, vectors)):
        db.add(
            KbChunk(
                library_id=row.library_id,
                document_id=row.id,
                chunk_index=index,
                text=text,
                embedding=json.dumps(vec, ensure_ascii=False),
                profile=profile,
            )
        )
    row.embedding_profile = profile
    return True


def score_chunks(db: Session, library_id: int, question: str, doc_ids: set[int] | None) -> dict[int, tuple[float, str]]:
    """每份资料最高的向量分和对应片段。"""

    if not question.strip() or not llm_public().get("has_key"):
        return {}
    try:
        query_vec = embed_texts([question])[0]
    except (ValueError, IndexError):
        return {}
    stmt = select(KbChunk).where(KbChunk.library_id == library_id, KbChunk.profile == embedding_profile())
    rows = list(db.scalars(stmt).all())
    best: dict[int, tuple[float, str]] = {}
    for row in rows:
        if doc_ids is not None and row.document_id not in doc_ids:
            continue
        score = cosine(query_vec, _parse_vec(row.embedding))
        if score < _VEC_FLOOR:
            continue
        prev = best.get(row.document_id)
        if prev is None or score > prev[0]:
            best[row.document_id] = (score, row.text)
    return best


def hybrid_rank(
    question: str,
    rows: list[KbDocument],
    chunk_best: dict[int, tuple[float, str]],
    top_k: int = 6,
) -> list[tuple[KbDocument, float, str]]:
    """关键词和向量取高分，带回最相关的一段原文。"""

    merged: list[tuple[KbDocument, float, str]] = []
    for row in rows:
        kw = score_document(question, row)
        vec, chunk = chunk_best.get(row.id, (0.0, ""))
        score = max(kw, vec)
        if score <= 0:
            continue
        raw = chunk if vec >= kw and chunk else ""
        snippet = expand_snippet(question, row, raw)
        merged.append((row, score, snippet))
    merged.sort(key=lambda item: item[1], reverse=True)
    return merged[:top_k]


def supplement_hits(
    question: str,
    rows: list[KbDocument],
    ranked: list[tuple[KbDocument, float, str]],
    chunk_best: dict[int, tuple[float, str]],
    top_k: int = 6,
) -> list[tuple[KbDocument, float, str]]:
    """问句里的实词前几份没盖住时，再按这些词补进来。已有的不丢。"""

    blobs = [_haystack(row) for row, _score, _snip in ranked]
    blobs.extend(snippet or "" for _row, _score, snippet in ranked)
    missing = uncovered_terms(question, blobs)
    if not missing:
        return ranked
    have = {row.id for row, _score, _snip in ranked}
    extra: list[tuple[KbDocument, float, str]] = []
    for row in rows:
        if row.id in have:
            continue
        blob = _haystack(row)
        if not any(term in blob for term in missing):
            continue
        kw = score_document(question, row)
        vec, chunk = chunk_best.get(row.id, (0.0, ""))
        score = max(kw, vec, 0.2)
        snippet = expand_snippet(" ".join(missing), row, chunk if vec >= kw and chunk else "")
        extra.append((row, score, snippet))
    extra.sort(key=lambda item: item[1], reverse=True)
    merged = list(ranked)
    for item in extra:
        merged.append(item)
        if len(merged) >= top_k + 4:
            break
    return merged
