"""知识库规则：回答风格和白话规则。"""

from __future__ import annotations

import json

from app.kb.models import KbLibrary

MODES = {"strict", "loose"}
VISION_ENGINES = {"vision", "ocr"}


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
    }


def dump_policy(
    wiki_enabled: bool,
    evidence_mode: str,
    rule: str,
    wiki_learn: bool = False,
    vision_enabled: bool = False,
    vision_engine: str = "vision",
) -> str:
    """写成 policy_json。Wiki 关着时不跟着提问更新。识图默认关。"""

    mode = evidence_mode if evidence_mode in MODES else "strict"
    enabled = bool(wiki_enabled)
    return json.dumps(
        {
            "wiki_enabled": enabled,
            "wiki_learn": enabled and bool(wiki_learn),
            "vision_enabled": bool(vision_enabled),
            "vision_engine": _vision_engine_of(vision_engine),
            "evidence_mode": mode,
            "rule": (rule or "").strip()[:500],
        },
        ensure_ascii=False,
    )


def resolve_mode(policy_mode: str, override: str | None) -> str:
    """当次覆盖优先，否则用库规则。"""

    if override in MODES:
        return override
    return policy_mode if policy_mode in MODES else "strict"
