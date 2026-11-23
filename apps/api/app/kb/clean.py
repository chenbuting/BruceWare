"""知识库清洗：把解析出来的字收成可供检索的一行。"""


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
