"""资料摘要：存在文档自己的 wiki_json 里。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from app.kb.models import KbDocument

WIKI_LIMIT = 400
ASK_WIKI_LIMIT = 5
_ENDS = "。．.？?！!\n\r"


def learn_hint(cited_count: int, updated_titles: list[str], truncated: bool) -> str:
    """没出处或一份都没更新：不提示。超过上限才说只改了前 5 份。"""

    if cited_count <= 0 or not updated_titles:
        return ""
    if truncated:
        return "本次回答了，只更新最相关的5份摘要，其余未改动。"
    names = "、".join(updated_titles)
    return f"已按这次问答更新了 {len(updated_titles)} 份摘要：{names}。"


@dataclass
class WikiNote:
    """一份资料上的摘要。"""

    summary: str
    updated_at: str
    source_hash: str
    stale: bool


def clip_summary(text: str, limit: int = WIKI_LIMIT) -> str:
    """超过字数时尽量按完整句子截断。"""

    text = (text or "").strip()
    if len(text) <= limit:
        return text
    window = text[:limit]
    pos = -1
    for index in range(len(window) - 1, -1, -1):
        if window[index] in _ENDS:
            pos = index
            break
    if pos >= 0:
        return window[: pos + 1].strip()
    return window


def parse_wiki(row: KbDocument) -> WikiNote:
    """读摘要。原文哈希变了只标可能过期，不删。"""

    raw = (row.wiki_json or "").strip()
    if not raw:
        return WikiNote("", "", "", False)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return WikiNote("", "", "", False)
    if not isinstance(data, dict):
        return WikiNote("", "", "", False)
    summary = str(data.get("summary") or "").strip()
    if not summary:
        return WikiNote("", "", "", False)
    source_hash = str(data.get("source_hash") or "")
    stale = source_hash != (row.file_hash or "")
    return WikiNote(
        summary=summary,
        updated_at=str(data.get("updated_at") or ""),
        source_hash=source_hash,
        stale=stale,
    )


def dump_wiki(summary: str, file_hash: str) -> str:
    """写成 wiki_json。"""

    return json.dumps(
        {
            "summary": summary,
            "updated_at": datetime.utcnow().isoformat(),
            "source_hash": file_hash or "",
        },
        ensure_ascii=False,
    )


def wiki_item(row: KbDocument, note: WikiNote) -> dict:
    """管理列表里的一条。"""

    return {
        "id": row.id,
        "title": row.title or row.file_name,
        "wiki_updated_at": note.updated_at,
        "wiki_stale": note.stale,
    }
