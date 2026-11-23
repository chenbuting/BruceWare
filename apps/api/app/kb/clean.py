"""知识库清洗：默认收成一行。勾上的做法按顺序做，特殊规则最后替换。"""

import re


def clean_text(text: str, limit: int | None = None) -> str:
    """去掉多余空白。limit 有值时再按字数截断。"""

    body = " ".join((text or "").split())
    if limit is None:
        return body
    return body[:limit]


def clean_choice(text: str, method: str, limit: int | None = None) -> str:
    """按选定的清洗方式处理。没认出的方式就收成一行。"""

    raw = text or ""
    if method == "keep":
        body = raw.strip()
    elif method == "blank":
        body = "\n".join(line.rstrip() for line in raw.splitlines() if line.strip())
    elif method == "dedupe":
        seen: set[str] = set()
        kept: list[str] = []
        for line in raw.splitlines():
            key = " ".join(line.split())
            if not key or key in seen:
                continue
            seen.add(key)
            kept.append(line.strip())
        body = "\n".join(kept)
    else:
        body = clean_text(raw)
    if limit is None:
        return body
    return body[:limit]


# 勾上的做法按这个顺序做。收成一行放最后，避免先把换行弄没。
_METHOD_ORDER = ("half", "punct", "mask", "page", "blank", "dedupe", "collapse")
_PUNCT = str.maketrans({",": "，", ";": "；", ":": "：", "!": "！", "?": "？", "(": "（", ")": "）"})
_PAGE = re.compile(r"^\s*(?:第\s*\d{1,4}\s*页(?:\s*/\s*共\s*\d{1,4}\s*页)?|[-—]\s*\d{1,4}\s*[-—]|page\s*\d{1,4})\s*$", re.I)
_PHONE = re.compile(r"(?<!\d)(1[3-9]\d)\d{4}(\d{4})(?!\d)")
_IDCARD = re.compile(r"(?<!\d)(\d{4})\d{10}(\d{3}[\dXx])(?!\d)")


def clean_document(
    text: str,
    methods: list[str] | None,
    rules: list[dict] | None = None,
    limit: int | None = None,
) -> tuple[str, list[dict]]:
    """按勾选的做法清洗，并给出每一类过了几条、挡了几条。"""

    selected = {item for item in _METHOD_ORDER if item in set(methods or [])}
    body = text or ""
    scores: dict[str, dict] = {}

    def add(name: str, passed: int, blocked: int) -> None:
        item = scores.setdefault(name, {"name": name, "passed": 0, "blocked": 0})
        item["passed"] += passed
        item["blocked"] += blocked

    norm_changed = 0
    if "half" in selected or "punct" in selected:
        lines = body.splitlines() or [body]
        changed_lines: list[str] = []
        for line in lines:
            nxt = _to_halfwidth(line) if "half" in selected else line
            if "punct" in selected:
                nxt = nxt.translate(_PUNCT)
            if nxt != line:
                norm_changed += 1
            changed_lines.append(nxt)
        body = "\n".join(changed_lines)
    if "mask" in selected:
        lines = body.splitlines() or [body]
        blocked = sum(1 for line in lines if _PHONE.search(line) or _IDCARD.search(line))
        add("安全性", len(lines) - blocked, blocked)
        body = _PHONE.sub(r"\1****\2", body)
        body = _IDCARD.sub(r"\1**********\2", body)
    if "page" in selected or "blank" in selected or "dedupe" in selected:
        lines = body.splitlines()
        if "page" in selected:
            kept = [line for line in lines if not _PAGE.match(line)]
            add("有效性", len(kept), len(lines) - len(kept))
            lines = kept
        if "blank" in selected:
            kept = [line for line in lines if line.strip()]
            add("完整性", len(kept), len(lines) - len(kept))
            lines = kept
        if "dedupe" in selected:
            seen: set[str] = set()
            kept = []
            blocked = 0
            for line in lines:
                key = " ".join(line.split())
                if not key or key in seen:
                    blocked += 1
                    continue
                seen.add(key)
                kept.append(line.rstrip())
            add("唯一性", len(kept), blocked)
            lines = kept
        body = "\n".join(lines)
    if "collapse" in selected or "half" in selected or "punct" in selected:
        parts = [line for line in body.splitlines() if line.strip()]
        if "collapse" in selected:
            body = clean_text(body)
            kept = 1 if body else 0
            # 收成一行后只留一条；字被改过的那条也算挡了。
            passed = kept if norm_changed == 0 else 0
            add("规范性", passed, max(0, len(parts) - passed))
        else:
            body = body.strip()
            examined = len(parts) or (1 if body else 0)
            add("规范性", max(0, examined - norm_changed), norm_changed)
    else:
        body = body.strip()
    rule_passed = 0
    rule_blocked = 0
    for rule in rules or []:
        find = str(rule.get("find") or "")
        if not find:
            continue
        count = body.count(find)
        if count:
            rule_blocked += count
            body = body.replace(find, str(rule.get("replace") or ""))
        else:
            rule_passed += 1
    if rules:
        add("自定义规则", rule_passed, rule_blocked)
    if limit is not None:
        body = body[:limit]
    order = ["完整性", "唯一性", "规范性", "有效性", "安全性", "自定义规则"]
    return body, [scores[name] for name in order if name in scores]


def _to_halfwidth(text: str) -> str:
    """全角数字、字母和符号转成半角。"""

    chars: list[str] = []
    for char in text:
        code = ord(char)
        if code == 0x3000:
            chars.append(" ")
        elif 0xFF01 <= code <= 0xFF5E:
            chars.append(chr(code - 0xFEE0))
        else:
            chars.append(char)
    return "".join(chars)
