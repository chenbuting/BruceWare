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


def alias_needles(question: str) -> list[str]:
    """简称补全称，方便 3C 对上强制性产品认证。"""

    q = (question or "").lower()
    extra: list[str] = []
    if re.search(r"3c|\bccc\b|强制性产品认证", q):
        extra.extend(["3c", "ccc", "强制性产品认证", "强制性产品", "国家强制性"])
    return extra


def snippet_needles(question: str) -> list[str]:
    """截文用的词：先简称和全称，再问句里比较实的词。"""

    skip = _FOCUS_SKIP | {"我们", "们有", "有多", "少张", "书吗", "共有", "证书吗"}
    terms: list[str] = []
    for item in alias_needles(question):
        if item not in terms:
            terms.append(item)
    for item in search_terms(question):
        if item in skip or item in terms:
            continue
        terms.append(item)
    terms.sort(key=lambda item: (0 if re.search(r"[a-z0-9]", item) else 1, -len(item)))
    return terms[:20]


def collect_snippet_windows(question: str, body: str, limit: int = 900, max_windows: int = 2) -> list[str]:
    """目录一段、后面正文再一段。两段离得近就只留一段。"""

    if not body:
        return []
    lower = body.lower()
    scored: list[tuple[int, int]] = []
    for term in snippet_needles(question):
        start = 0
        found = 0
        while found < 6:
            pos = lower.find(term, start)
            if pos < 0:
                break
            scored.append((pos, len(term)))
            start = pos + max(len(term), 1)
            found += 1
    if not scored:
        return [body[:limit]]
    scored.sort(key=lambda item: (-item[1], item[0]))
    picked: list[int] = []
    gap = int(limit * 0.7)
    for pos, _weight in scored:
        if any(abs(pos - prev) < gap for prev in picked):
            continue
        picked.append(pos)
        if len(picked) >= max_windows:
            break
    picked.sort()
    return [body[max(0, pos - 80) : max(0, pos - 80) + limit] for pos in picked]


def snippet_of(question: str, row: KbDocument, limit: int = 900) -> str:
    """截靠近问句的正文。目录和后面相关段都能带到。"""

    body = (row.search_text or "").strip()
    if not body:
        return (row.title or row.file_name or "")[:limit]
    windows = collect_snippet_windows(question, body, limit=limit)
    if not windows:
        return body[:limit]
    return "\n\n".join(windows)[: limit * 2 + 200]


_FOCUS_SKIP = {
    "什么",
    "多少",
    "哪个",
    "哪些",
    "怎么",
    "如何",
    "一下",
    "这个",
    "那个",
    "还有",
    "以及",
    "请问",
    "可以",
    "是否",
    "有没有",
    "相关",
    "资料",
    "文件",
}


def focus_terms(question: str) -> list[str]:
    """问句里比较实的词，用来看检索有没有盖住。不用二字切片，避免乱补。"""

    cleaned = question.strip().lower()
    if not cleaned:
        return []
    found = re.findall(r"[a-z0-9_]{2,}|[\u4e00-\u9fff]{2,}", cleaned)
    terms: list[str] = []
    for token in found:
        if token in _FOCUS_SKIP:
            continue
        if re.fullmatch(r"[a-z0-9_]+", token):
            if token not in terms:
                terms.append(token)
            continue
        if 2 <= len(token) <= 6 and token not in terms:
            terms.append(token)
        if len(token) >= 4:
            for index in range(0, len(token) - 3):
                piece = token[index : index + 4]
                if piece not in _FOCUS_SKIP and piece not in terms:
                    terms.append(piece)
    return terms[:16]


def _term_in_blob(term: str, blob: str) -> bool:
    if term in blob:
        return True
    if len(term) >= 3:
        for index in range(len(term) - 2):
            if term[index : index + 3] in blob:
                return True
    return False


def uncovered_terms(question: str, blobs: list[str]) -> list[str]:
    """前几份资料没盖住的实词。"""

    hay = "\n".join(item.lower() for item in blobs if item)
    return [term for term in focus_terms(question) if not _term_in_blob(term, hay)]


def expand_snippet(question: str, row: KbDocument, piece: str = "", limit: int = 900) -> str:
    """命中附近尽量给够。向量命中的那段也留着。"""

    text = snippet_of(question, row, limit)
    extra = (piece or "").strip()
    if extra and extra not in text:
        return f"{extra}\n\n{text}"[: limit * 2 + 200]
    return text


def rank_documents(question: str, rows: list[KbDocument], top_k: int = 6) -> list[tuple[KbDocument, float]]:
    scored = [(row, score_document(question, row)) for row in rows]
    scored = [item for item in scored if item[1] > 0]
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:top_k]
