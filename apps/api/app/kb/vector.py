"""知识库文本向量：切段、入库、和关键词一起打分。"""

from __future__ import annotations

import hashlib
import json
import math

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ai import can_embed, embed_texts, embedding_profile
from app.kb.models import KbChunk, KbDocument
from app.kb.search import _haystack, score_document, snippet_of, uncovered_terms

_CHUNK_SIZE = 400
_CHUNK_OVERLAP = 60
_MAX_CHUNKS = 40
_VEC_FLOOR = 0.28
_PER_DOC_CHUNKS = 3
_INDEX_GAP = 1
_ASK_CHUNK_LIMIT = 10

# 一份资料：最高分，以及候选块 (块序号, 分数, 正文)
type ChunkPick = tuple[int, float, str]
type DocHits = dict[int, tuple[float, list[ChunkPick]]]


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


def list_chunks(db: Session, document_id: int) -> list[KbChunk]:
    return list(
        db.scalars(select(KbChunk).where(KbChunk.document_id == document_id).order_by(KbChunk.chunk_index.asc(), KbChunk.id.asc())).all()
    )


VECTOR_HINTS = {
    "updated": "字已保存，这份资料的向量已更新。",
    "updated_chunk": "字已保存，这一块的向量已更新。",
    "no_key": "字已保存，但没填 AI Key，向量没更新。",
    "failed": "字已保存，向量更新失败，提问可能还按旧的找。",
    "skipped_edited": "字已保存，能按关键词搜。但这份有手改过的切片，没整份重算向量。",
    "skipped": "字已保存，向量没有重算。",
    "pending": "字已保存。改完后点「重算向量」。",
    "rebuilt": "这份资料的向量已重算。",
}


def _fail_status(exc: BaseException) -> str:
    text = str(exc).replace("\n", " ").strip()
    return f"failed:{text[:160]}" if text else "failed"


def vector_payload(status: str, *, chunk: bool = False) -> dict:
    """给保存接口带上向量有没有更新。"""

    if status.startswith("failed:"):
        return {
            "vector_ok": False,
            "vector_hint": f"字已保存，向量更新失败：{status[7:].strip()}",
        }
    key = "updated_chunk" if status == "updated" and chunk else status
    return {
        "vector_ok": status == "updated",
        "vector_hint": VECTOR_HINTS.get(key, VECTOR_HINTS["failed"]),
    }


def content_stamp(row: KbDocument, chunks: list[KbChunk] | None = None) -> str:
    """正文、标题、标签、切片变了，这个戳就会变。"""

    chunk_blob = "\n".join(f"{item.chunk_index}:{(item.text or '').strip()}" for item in (chunks or []))
    raw = f"{row.file_hash or ''}\n{row.title or ''}\n{row.tags or ''}\n{row.search_text or ''}\n{chunk_blob}"
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:24]


def mark_vector_ready(row: KbDocument, chunks: list[KbChunk] | None = None) -> None:
    """向量算成功后记下：当前模型和这份内容对得上。"""

    row.embedding_profile = embedding_profile()
    row.vector_stamp = content_stamp(row, chunks)


def document_vector_state(db: Session, row: KbDocument) -> str:
    """none 未向量，ready 已向量，stale 内容或模型变了要重算。"""

    current = embedding_profile()
    chunks = list_chunks(db, row.id)
    with_vec = [item for item in chunks if (item.embedding or "").strip() not in {"", "[]"}]
    if not with_vec:
        return "none"
    current_ok = [item for item in with_vec if (item.profile or "") == current]
    if not current_ok or len(current_ok) < len(chunks):
        return "stale"
    now = content_stamp(row, chunks)
    stamp = row.vector_stamp or ""
    profile = row.embedding_profile or ""
    if not stamp:
        # 老数据没戳：没手改过就先记下当前内容，以后改了才能看出来
        if any(item.edited for item in chunks):
            return "stale"
        if profile in {"", current}:
            row.embedding_profile = current
            row.vector_stamp = now
            return "ready"
        return "stale"
    if profile != current or stamp != now:
        return "stale"
    return "ready"


def chunk_dict(row: KbChunk) -> dict:
    preview = (row.text or "").replace("\n", " ").strip()
    return {
        "id": row.id,
        "index": row.chunk_index,
        "text": row.text or "",
        "edited": bool(row.edited),
        "preview": preview[:80],
    }


def ensure_chunks(db: Session, row: KbDocument) -> list[KbChunk]:
    """没有切片时先切好。有 Key 就做向量；改过的块不会被整份重切冲掉。"""

    existing = list_chunks(db, row.id)
    if existing:
        return existing
    index_document(db, row)
    existing = list_chunks(db, row.id)
    if existing:
        return existing
    body = (row.search_text or "").strip()
    parts = split_chunks(f"{row.title or ''} {row.tags or ''} {body}")
    if not parts:
        return []
    for index, text in enumerate(parts):
        db.add(
            KbChunk(
                library_id=row.library_id,
                document_id=row.id,
                chunk_index=index,
                text=text,
                embedding="",
                profile="",
                edited=0,
            )
        )
    db.flush()
    return list_chunks(db, row.id)


def update_chunk_text(db: Session, row: KbChunk, text: str) -> tuple[KbChunk, str]:
    """改一块的字，并尽量重算这一块的向量。返回这块和结果：updated / no_key / failed。"""

    row.text = (text or "").strip()
    row.edited = 1
    if not row.text:
        return row, "failed"
    if not can_embed():
        return row, "no_key"
    try:
        vectors = embed_texts([row.text])
    except Exception as exc:
        return row, _fail_status(exc)
    if not vectors:
        return row, "failed"
    row.embedding = json.dumps(vectors[0], ensure_ascii=False)
    row.profile = embedding_profile()
    doc = db.get(KbDocument, row.document_id)
    if doc is not None:
        mark_vector_ready(doc, list_chunks(db, doc.id))
    return row, "updated"


def index_document(db: Session, row: KbDocument, force: bool = False) -> str:
    """抽出正文后写入向量。返回 updated / skipped / skipped_edited / no_key / failed。"""

    edited = db.scalar(select(KbChunk.id).where(KbChunk.document_id == row.id, KbChunk.edited == 1).limit(1))
    if edited:
        return "skipped_edited"
    if not can_embed():
        return "no_key"
    profile = embedding_profile()
    if not force:
        chunks = list_chunks(db, row.id)
        stamp = row.vector_stamp or ""
        now = content_stamp(row, chunks) if chunks else ""
        current_ok = [item for item in chunks if (item.profile or "") == profile and (item.embedding or "").strip() not in {"", "[]"}]
        if chunks and len(current_ok) == len(chunks) and (not stamp or stamp == now):
            if (row.embedding_profile or "") != profile or (row.vector_stamp or "") != now:
                mark_vector_ready(row, chunks)
            return "skipped"
        if chunks and (row.embedding_profile or "") == profile and (not stamp or stamp == now):
            return "skipped"
    body = (row.search_text or "").strip()
    if not body:
        return "failed"
    parts = split_chunks(f"{row.title or ''} {row.tags or ''} {body}")
    if not parts:
        return "failed"
    try:
        vectors = embed_texts(parts)
    except Exception as exc:
        return _fail_status(exc)
    if len(vectors) != len(parts):
        return "failed:向量条数对不上"
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
    db.flush()
    mark_vector_ready(row, list_chunks(db, row.id))
    return "updated"


def _pick_spread(scored: list[ChunkPick], limit: int = _PER_DOC_CHUNKS, gap: int = _INDEX_GAP) -> list[ChunkPick]:
    """按分数取块，彼此隔开，避免全挤在目录附近。"""

    picked: list[ChunkPick] = []
    for item in scored:
        if any(abs(item[0] - prev[0]) < gap for prev in picked):
            continue
        picked.append(item)
        if len(picked) >= limit:
            break
    return picked


def _with_neighbors(by_index: dict[int, tuple[float, str]], picked: list[ChunkPick], best_index: int) -> list[ChunkPick]:
    """最高分那块带上左右邻居，半句话能接上。"""

    have = {item[0] for item in picked}
    extra: list[ChunkPick] = []
    for index in (best_index - 1, best_index + 1):
        if index in by_index and index not in have:
            score, text = by_index[index]
            extra.append((index, score, text))
            have.add(index)
    merged = list(picked) + extra
    merged.sort(key=lambda item: item[0])
    return merged


def _join_picks(picks: list[ChunkPick]) -> str:
    return "\n\n".join(text.strip() for _index, _score, text in picks if (text or "").strip())


def _priority_picks(picks: list[ChunkPick]) -> list[ChunkPick]:
    """先保住最高分和它的邻居，再补其它分散块。"""

    if not picks:
        return []
    best_index = max(picks, key=lambda item: item[1])[0]
    best = [item for item in picks if item[0] == best_index]
    neighbors = [item for item in picks if abs(item[0] - best_index) == 1]
    others = [item for item in picks if item[0] != best_index and abs(item[0] - best_index) != 1]
    others.sort(key=lambda item: item[1], reverse=True)
    return best + neighbors + others


def pack_ask_snippets(
    question: str,
    ranked: list[tuple[KbDocument, float, list[ChunkPick]]],
    limit: int = _ASK_CHUNK_LIMIT,
) -> list[tuple[KbDocument, float, str]]:
    """每份先留一块，剩下来的名额给前面的资料。合计不超过上限。"""

    queues = [_priority_picks(picks) for _row, _score, picks in ranked]
    assigned: list[list[ChunkPick]] = [[] for _ in ranked]
    budget = limit
    for index, queue in enumerate(queues):
        if queue and budget > 0:
            assigned[index].append(queue.pop(0))
            budget -= 1
    for index, queue in enumerate(queues):
        while queue and budget > 0:
            assigned[index].append(queue.pop(0))
            budget -= 1
    packed: list[tuple[KbDocument, float, str]] = []
    for (row, score, _picks), picks in zip(ranked, assigned):
        picks.sort(key=lambda item: item[0])
        snippet = _join_picks(picks) if picks else snippet_of(question, row)
        packed.append((row, score, snippet))
    return packed


def score_chunks(db: Session, library_id: int, question: str, doc_ids: set[int] | None) -> DocHits:
    """每份资料按向量挑出分散的几块，并带上最高分左右邻居。"""

    if not question.strip() or not can_embed():
        return {}
    try:
        query_vec = embed_texts([question])[0]
    except (ValueError, IndexError):
        return {}
    stmt = select(KbChunk).where(KbChunk.library_id == library_id, KbChunk.profile == embedding_profile())
    rows = list(db.scalars(stmt).all())
    grouped: dict[int, list[ChunkPick]] = {}
    for row in rows:
        if doc_ids is not None and row.document_id not in doc_ids:
            continue
        score = cosine(query_vec, _parse_vec(row.embedding))
        grouped.setdefault(row.document_id, []).append((row.chunk_index, score, row.text or ""))
    best: DocHits = {}
    for document_id, items in grouped.items():
        by_index = {index: (score, text) for index, score, text in items}
        candidates = [item for item in items if item[1] >= _VEC_FLOOR]
        if not candidates:
            continue
        candidates.sort(key=lambda item: item[1], reverse=True)
        spread = _pick_spread(candidates)
        selected = _with_neighbors(by_index, spread, candidates[0][0])
        best[document_id] = (candidates[0][1], selected)
    return best


def hybrid_rank(
    question: str,
    rows: list[KbDocument],
    chunk_best: DocHits,
    top_k: int = 6,
) -> list[tuple[KbDocument, float, list[ChunkPick]]]:
    """关键词和向量取高分，先带回候选块，稍后按上限再裁。"""

    merged: list[tuple[KbDocument, float, list[ChunkPick]]] = []
    for row in rows:
        kw = score_document(question, row)
        vec, pieces = chunk_best.get(row.id, (0.0, []))
        score = max(kw, vec)
        if score <= 0:
            continue
        merged.append((row, score, pieces))
    merged.sort(key=lambda item: item[1], reverse=True)
    return merged[:top_k]


def supplement_hits(
    question: str,
    rows: list[KbDocument],
    ranked: list[tuple[KbDocument, float, list[ChunkPick]]],
    chunk_best: DocHits,
    top_k: int = 6,
) -> list[tuple[KbDocument, float, list[ChunkPick]]]:
    """问句里的实词前几份没盖住时，再按这些词补进来。已有的不丢。"""

    blobs = [_haystack(row) for row, _score, _picks in ranked]
    blobs.extend(text for _row, _score, picks in ranked for _index, _s, text in picks)
    missing = uncovered_terms(question, blobs)
    if not missing:
        return ranked
    have = {row.id for row, _score, _picks in ranked}
    extra: list[tuple[KbDocument, float, list[ChunkPick]]] = []
    for row in rows:
        if row.id in have:
            continue
        blob = _haystack(row)
        if not any(term in blob for term in missing):
            continue
        kw = score_document(question, row)
        vec, pieces = chunk_best.get(row.id, (0.0, []))
        extra.append((row, max(kw, vec, 0.2), pieces))
    extra.sort(key=lambda item: item[1], reverse=True)
    merged = list(ranked)
    for item in extra:
        merged.append(item)
        if len(merged) >= top_k + 4:
            break
    return merged
