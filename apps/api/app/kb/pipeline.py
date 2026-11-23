"""知识库入库流水线。只在知识库内使用。

解析、清洗的参数来自这个库的设置。没填就用现在这套。
"""

from __future__ import annotations

import json

from app.kb.extract import extract_search_text
from app.kb.models import KbDocument


def search_text_for_index(file_name: str, data: bytes, policy: dict | None = None) -> str:
    """按本库的解析和清洗设置抽出检索正文。预览原文不要走这里。"""

    rules = policy or {}
    collapse = bool(rules.get("clean_collapse", True))
    return extract_search_text(
        file_name,
        data,
        collapse=collapse,
        text_limit=rules.get("text_limit") or None,
        sheet_limit=rules.get("sheet_limit") or None,
        sheet_rows=rules.get("sheet_rows") or None,
    )


def remember_parsed(row: KbDocument, text: str) -> None:
    """记下解析原文。不冲掉图是否抽过等其它记录。"""

    data = _extra(row)
    data["parsed_text"] = text or ""
    row.extra = json.dumps(data, ensure_ascii=False)


def normalize_flow(raw: dict | None) -> dict:
    """整理一份资料的处理方式。认不出的选项就退回现在这套。"""

    data = raw or {}
    parse = str(data.get("parse") or "standard")
    chunk = str(data.get("chunk") or "chars")
    if parse not in {"standard", "head"}:
        parse = "standard"
    cleans = _cleans(data.get("cleans", data.get("clean")))
    rules = _rules(data.get("rules"))
    if chunk not in {"chars", "paragraph", "whole"}:
        chunk = "chars"
    try:
        size = int(data.get("chunk_size"))
    except (TypeError, ValueError):
        size = 400
    size = min(2000, max(80, size))
    try:
        overlap = int(data.get("chunk_overlap"))
    except (TypeError, ValueError):
        overlap = 60
    if overlap < 0 or overlap >= size:
        overlap = 60 if 60 < size else 0
    try:
        max_chunks = int(data.get("max_chunks"))
    except (TypeError, ValueError):
        max_chunks = 40
    max_chunks = min(200, max(5, max_chunks))
    return {
        "parse": parse,
        "cleans": cleans,
        "rules": rules,
        "chunk": chunk,
        "vector": bool(data.get("vector", True)),
        "chunk_size": size,
        "chunk_overlap": overlap,
        "max_chunks": max_chunks,
    }


def _cleans(raw) -> list[str]:
    """勾选的清洗做法。旧数据只有一个词时，收成一行仍是默认。"""

    allowed = {"half", "punct", "mask", "page", "blank", "dedupe", "collapse"}
    if isinstance(raw, str):
        if raw == "blank":
            return ["blank"]
        if raw == "dedupe":
            return ["dedupe"]
        if raw == "keep":
            return []
        return ["collapse"]
    if not isinstance(raw, list):
        return ["collapse"]
    picked = [str(item) for item in raw if str(item) in allowed]
    return picked


def _rules(raw) -> list[dict]:
    """用户自己加的替换。空的找到内容不算。最多 20 条。"""

    if not isinstance(raw, list):
        return []
    rules: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        find = str(item.get("find") or "").strip()[:80]
        if not find:
            continue
        rules.append({"find": find, "replace": str(item.get("replace") or "")[:80]})
        if len(rules) >= 20:
            break
    return rules


def stored_flow(row: KbDocument) -> dict | None:
    """这份资料点过「按这个处理」才有记录。没点过就是还用原来的做法。"""

    raw = _extra(row).get("flow")
    if not isinstance(raw, dict):
        return None
    return normalize_flow(raw)


def flow_view(row: KbDocument) -> dict:
    """给预览表单用。没处理过也返回默认选项。"""

    saved = stored_flow(row)
    view = normalize_flow(saved)
    view["saved"] = saved is not None
    return view


def remember_flow(row: KbDocument, flow: dict) -> None:
    """记下这一份的处理方式，不冲掉图是否抽过等其它记录。"""

    data = _extra(row)
    data["flow"] = normalize_flow(flow)
    row.extra = json.dumps(data, ensure_ascii=False)


def _extra(row: KbDocument) -> dict:
    raw = (row.extra or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}
