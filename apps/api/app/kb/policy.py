"""知识库规则：回答风格和白话规则。"""

from __future__ import annotations

import json

from app.kb.models import KbLibrary

MODES = {"strict", "loose"}


def parse_policy(row: KbLibrary) -> dict:
    """读库规则。缺省：关 Wiki、严格出处、没有额外规则。"""

    default = {"wiki_enabled": False, "evidence_mode": "strict", "rule": ""}
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
    return {
        "wiki_enabled": bool(data.get("wiki_enabled")),
        "evidence_mode": mode,
        "rule": str(data.get("rule") or "").strip()[:500],
    }


def dump_policy(wiki_enabled: bool, evidence_mode: str, rule: str) -> str:
    """写成 policy_json。"""

    mode = evidence_mode if evidence_mode in MODES else "strict"
    return json.dumps(
        {
            "wiki_enabled": bool(wiki_enabled),
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
