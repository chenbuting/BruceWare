"""知识库规则：回答风格和白话规则。"""

from __future__ import annotations

import json

from app.kb.models import KbLibrary

MODES = {"strict", "loose"}
VISION_ENGINES = {"vision", "ocr"}
AUDIT_MODES = {"off", "rules"}


def _audit_mode_of(raw) -> str:
    value = str(raw or "rules").strip()
    return value if value in AUDIT_MODES else "rules"


def _vision_engine_of(raw) -> str:
    value = str(raw or "vision").strip()
    return value if value in VISION_ENGINES else "vision"


def parse_policy(row: KbLibrary) -> dict:
    """读库规则。缺省：关 Wiki、严格出处、没有额外规则。"""

    default = {
        "wiki_enabled": False,
        "wiki_learn": False,
        "vision_enabled": False,
        "vision_engine": "vision",
        "evidence_mode": "strict",
        "rule": "",
        "text_limit": 20000,
        "sheet_limit": 40000,
        "sheet_rows": 500,
        "clean_collapse": True,
        "chunk_size": 400,
        "chunk_overlap": 60,
        "max_chunks": 40,
        "vector_enabled": True,
        "link_enabled": False,
        "link_hops": 3,
        "audit_mode": "rules",
    }
    raw = (row.policy_json or "").strip()
    if not raw:
        return default
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return default
    if not isinstance(data, dict):
        return default
    mode = str(data.get("evidence_mode") or "strict")
    if mode not in MODES:
        mode = "strict"
    wiki_enabled = bool(data.get("wiki_enabled"))
    return {
        "wiki_enabled": wiki_enabled,
        "wiki_learn": wiki_enabled and bool(data.get("wiki_learn")),
        "vision_enabled": bool(data.get("vision_enabled")),
        "vision_engine": _vision_engine_of(data.get("vision_engine")),
        "evidence_mode": mode,
        "rule": str(data.get("rule") or "").strip()[:500],
        "text_limit": _bounded(data.get("text_limit"), 20000, 1000, 100000),
        "sheet_limit": _bounded(data.get("sheet_limit"), 40000, 1000, 200000),
        "sheet_rows": _bounded(data.get("sheet_rows"), 500, 20, 5000),
        "clean_collapse": _flag(data, "clean_collapse", True),
        "chunk_size": _chunk_size(data.get("chunk_size")),
        "chunk_overlap": _chunk_overlap(data.get("chunk_overlap"), _chunk_size(data.get("chunk_size"))),
        "max_chunks": _bounded(data.get("max_chunks"), 40, 5, 200),
        "vector_enabled": _flag(data, "vector_enabled", True),
        "link_enabled": _flag(data, "link_enabled", False),
        "link_hops": _bounded(data.get("link_hops"), 3, 1, 8),
        "audit_mode": _audit_mode_of(data.get("audit_mode")),
    }


def _bounded(raw, default: int, low: int, high: int) -> int:
    """没填或填坏了就用默认。超出范围就收到边界里。"""

    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    if value < low:
        return low
    if value > high:
        return high
    return value


def _flag(data: dict, key: str, default: bool) -> bool:
    if key not in data:
        return default
    return bool(data.get(key))


def _chunk_size(raw) -> int:
    """切片长度。没填或填坏了就用 400。"""

    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 400
    if value < 80:
        return 80
    if value > 2000:
        return 2000
    return value


def _chunk_overlap(raw, size: int) -> int:
    """重叠字数。不能大于等于切片长度，避免切段停不住。"""

    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 60
    if value < 0:
        value = 0
    if value >= size:
        return max(0, size // 5)
    return value


def dump_policy(
    wiki_enabled: bool,
    evidence_mode: str,
    rule: str,
    wiki_learn: bool = False,
    vision_enabled: bool = False,
    vision_engine: str = "vision",
    chunk_size: int = 400,
    chunk_overlap: int = 60,
    text_limit: int = 20000,
    sheet_limit: int = 40000,
    sheet_rows: int = 500,
    clean_collapse: bool = True,
    max_chunks: int = 40,
    vector_enabled: bool = True,
    link_enabled: bool = False,
    link_hops: int = 3,
    audit_mode: str = "rules",
) -> str:
    """写成 policy_json。Wiki 关着时不跟着提问更新。识图默认关。关联补查默认关。"""

    mode = evidence_mode if evidence_mode in MODES else "strict"
    enabled = bool(wiki_enabled)
    size = _chunk_size(chunk_size)
    return json.dumps(
        {
            "wiki_enabled": enabled,
            "wiki_learn": enabled and bool(wiki_learn),
            "vision_enabled": bool(vision_enabled),
            "vision_engine": _vision_engine_of(vision_engine),
            "evidence_mode": mode,
            "rule": (rule or "").strip()[:500],
            "text_limit": _bounded(text_limit, 20000, 1000, 100000),
            "sheet_limit": _bounded(sheet_limit, 40000, 1000, 200000),
            "sheet_rows": _bounded(sheet_rows, 500, 20, 5000),
            "clean_collapse": bool(clean_collapse),
            "chunk_size": size,
            "chunk_overlap": _chunk_overlap(chunk_overlap, size),
            "max_chunks": _bounded(max_chunks, 40, 5, 200),
            "vector_enabled": bool(vector_enabled),
            "link_enabled": bool(link_enabled),
            "link_hops": _bounded(link_hops, 3, 1, 8),
            "audit_mode": _audit_mode_of(audit_mode),
        },
        ensure_ascii=False,
    )


def resolve_mode(policy_mode: str, override: str | None) -> str:
    """当次覆盖优先，否则用库规则。"""

    if override in MODES:
        return override
    return policy_mode if policy_mode in MODES else "strict"
