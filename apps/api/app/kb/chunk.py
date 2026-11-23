"""知识库切片：把洗干净的正文切成段。"""

from app.kb.clean import clean_text

_CHUNK_SIZE = 400
_CHUNK_OVERLAP = 60
_MAX_CHUNKS = 40


def split_chunks(
    text: str,
    size: int = _CHUNK_SIZE,
    overlap: int = _CHUNK_OVERLAP,
    limit: int = _MAX_CHUNKS,
    collapse: bool = True,
) -> list[str]:
    """按字数切段，相邻留一点重叠。不传参数时就是现在这套：400 字、重叠 60。"""

    body = clean_text(text) if collapse else (text or "").strip()
    if not body:
        return []
    size = size if size >= 50 else _CHUNK_SIZE
    overlap = overlap if overlap >= 0 else _CHUNK_OVERLAP
    if overlap >= size:
        overlap = 0
    if len(body) <= size:
        return [body]
    parts: list[str] = []
    start = 0
    while start < len(body) and len(parts) < limit:
        parts.append(body[start : start + size])
        start += size - overlap
    return parts


def split_paragraphs(text: str, limit: int = _MAX_CHUNKS) -> list[str]:
    """按空行分段。没有空行时按每一行分。最多留 limit 段。"""

    body = (text or "").strip()
    if not body:
        return []
    parts = [item.strip() for item in body.split("\n\n") if item.strip()]
    if len(parts) <= 1:
        parts = [item.strip() for item in body.splitlines() if item.strip()]
    cap = limit if limit > 0 else _MAX_CHUNKS
    return parts[:cap]


def split_whole(text: str, limit: int = 20000) -> list[str]:
    """整篇当成一段。"""

    body = (text or "").strip()
    if not body:
        return []
    return [body[:limit]]
