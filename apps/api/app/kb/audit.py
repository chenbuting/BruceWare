"""回答自检：对照本轮原文，检查回答有没有依据、有没有乱引、有没有漏标冲突。

只读，不改回答，不发请求，不读盘。任何异常都收在函数内，返回 audit_failed。
"""

from __future__ import annotations

import re
import time
from decimal import Decimal, InvalidOperation

_MAX_ITEMS = 12

_ABSOLUTE = (
    "整个库都没有",
    "整个知识库都没有",
    "库里没有",
    "库中不存在",
    "已穷举",
    "全部资料都没有",
    "没有任何资料",
)
_STRICT_HINTS = ("【推断】", "以下为推断", "可能", "大概", "也许", "推测")
_CONCLUSION = ("可以通过", "可以批准", "建议批准", "判定为合格", "结论是合格")
_FIELDS = ("有效期", "质保期", "保修期", "截止日期", "截止", "到期日", "到期", "期限", "金额", "价款", "编号", "日期")
_STOP_TERMS = {
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
    "我们",
    "他们",
    "就是",
    "能否",
    "帮我",
    "看看",
}

_DATE_YMD = re.compile(r"(\d{4})\s*[-/年]\s*(\d{1,2})\s*[-/月]\s*(\d{1,2})\s*日?")
_DATE_YM = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月")
_AMOUNT = re.compile(r"(?:¥|￥)?\s*(\d[\d,，]*(?:\.\d+)?)\s*(亿元|万元|元)")
_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*[%％]")
_DURATION = re.compile(r"(\d+(?:\.\d+)?)\s*(个月|年|天|日|份|项|次|页)")
_ID_TOKEN = re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9][A-Za-z0-9\-_]{5,}(?![A-Za-z0-9])")
_QUOTE = re.compile(r"[“\"「]([^”\"」]{4,60})[”\"」]")
_CITED = re.compile(r"资料\s*(\d+)")


def audit_answer(
    question: str,
    answer: str,
    citations: list[dict] | None,
    ranked_full: list | None,
    *,
    mode: str = "strict",
    ask_kind: str = "answer",
    enabled: bool = True,
) -> dict:
    """给一段回答打分。返回 status / score / items / checked / elapsed_ms。"""

    started = time.perf_counter()
    if not enabled:
        return {"status": "ok", "score": 1.0, "items": [], "checked": 0, "elapsed_ms": 0, "enabled": False}
    try:
        result = _audit(
            question or "",
            (answer or "").strip(),
            list(citations or []),
            list(ranked_full or []),
            mode=mode,
            ask_kind=ask_kind,
        )
    except Exception as exc:  # 自检失败不能影响回答
        result = {
            "status": "error",
            "score": 0.0,
            "items": [{"code": "audit_failed", "severity": "error", "message": f"自检未完成：{str(exc)[:120]}"}],
            "checked": 0,
            "enabled": True,
        }
    result["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
    result["enabled"] = True
    return result


def _audit(question: str, answer: str, citations: list[dict], ranked_full: list, *, mode: str, ask_kind: str) -> dict:
    items: list[dict] = []

    def add(code: str, severity: str, message: str, *, claim: str = "", refs: list[dict] | None = None) -> None:
        if len(items) >= _MAX_ITEMS:
            return
        item = {"code": code, "severity": severity, "message": message}
        if claim:
            item["claim"] = claim
        if refs:
            item["refs"] = refs
        items.append(item)

    if not answer:
        add("empty_answer", "error", "回答是空的")
        return _finish(items, checked=1)

    cites = _clean_citations(citations)
    used = {int(number) for number in _CITED.findall(answer)}
    docs = _doc_map(ranked_full)
    snippets = {doc_id: item["snippet"] for doc_id, item in docs.items()}
    titles = {doc_id: item["title"] for doc_id, item in docs.items()}
    for item in cites:
        titles.setdefault(item["id"], item["title"])
    cites_by_index = {item["index"]: item for item in cites}

    # 1. 引用结构与范围（拿资料模式只看形状，不要求正文里写「资料N」）
    if ask_kind != "materials":
        out_of_range = sorted(number for number in used if number not in cites_by_index)
        if out_of_range:
            add("citation_out_of_range", "error", f"回答引用了不存在的资料：资料{out_of_range[0]}")
        if cites and not used:
            add("citation_missing", "warn", "回答没有引用任何出处，但本轮检索到了资料")
        if not out_of_range:
            unused = [item for item in cites if item["index"] not in used]
            for item in unused[:2]:
                add(
                    "citation_not_used",
                    "info",
                    f"资料{item['index']} 列在出处里，但回答没有用到它的内容",
                    refs=[{"citation": item["index"], "id": item["id"], "title": item["title"]}],
                )
            if len(unused) > 2:
                add("citation_not_used_more", "info", f"另有 {len(unused) - 2} 份资料列在出处里但没有用到")

    # 2. 事实核对（核心）。拿资料模式交的是文件清单，不核对正文事实。
    facts = [] if ask_kind == "materials" else _extract_facts(answer)
    snippet_norm = {doc_id: _norm(text) for doc_id, text in snippets.items()}
    snippet_facts = {doc_id: _fact_set(text) for doc_id, text in snippets.items()}
    all_norm = "\n".join(snippet_norm.values())
    all_facts: set[str] = set()
    for values in snippet_facts.values():
        all_facts |= values
    used_ids = [cites_by_index[i]["id"] for i in sorted(used) if i in cites_by_index]
    cited_norm = "\n".join(snippet_norm.get(doc_id, "") for doc_id in used_ids)
    cited_facts: set[str] = set()
    for doc_id in used_ids:
        cited_facts |= snippet_facts.get(doc_id, set())
    supported: list[str] = []
    for fact in facts:
        if _fact_supported(fact, cited_norm, cited_facts):
            supported.append(fact["canon"])
            continue
        if used_ids and _fact_supported(fact, all_norm, all_facts):
            refs = [
                {"citation": item["index"], "id": item["id"], "title": item["title"]}
                for item in cites
                if _fact_supported(fact, snippet_norm.get(item["id"], ""), snippet_facts.get(item["id"], set()))
            ]
            if not refs:
                refs = [
                    {"citation": 0, "id": doc_id, "title": titles.get(doc_id, "")}
                    for doc_id, text_norm in snippet_norm.items()
                    if _fact_supported(fact, text_norm, snippet_facts.get(doc_id, set()))
                ]
            add(
                "fact_in_uncited_doc",
                "warn",
                f"回答里的「{fact['raw']}」出现在本轮资料里，但没有列进出处",
                claim=fact["raw"],
                refs=refs,
            )
        else:
            add("unsupported_fact", "warn", f"回答里的「{fact['raw']}」在本轮原文里找不到", claim=fact["raw"])

    # 3. 被引资料是否真的支撑了什么
    if facts and supported:
        for item in cites:
            if item["index"] not in used:
                continue
            doc_id = item["id"]
            text_norm = snippet_norm.get(doc_id, "")
            own = snippet_facts.get(doc_id, set())
            if not any(_fact_supported(fact, text_norm, own) for fact in facts if fact["canon"] in supported):
                add(
                    "weak_citation",
                    "warn",
                    f"资料{item['index']} 被列为出处，但片段里找不到回答中的具体说法",
                    refs=[{"citation": item["index"], "id": item["id"], "title": item["title"]}],
                )

    # 4. 口径与诚实性
    for phrase in _ABSOLUTE:
        if phrase in answer:
            add("absolute_claim", "warn", f"回答用了绝对说法「{phrase}」；本轮没见到不等于库里没有", claim=phrase)
            break
    if mode == "strict":
        for hint in _STRICT_HINTS:
            if hint in answer:
                add("strict_inference", "warn", f"严格模式回答里出现了推测词「{hint}」", claim=hint)
                break

    conflict = _field_conflicts({doc_id: snippets.get(doc_id, "") for doc_id in used_ids}, answer)
    if conflict:
        add("conflict_missed", "info", conflict)

    missing = _coverage_gap(question, "\n".join(snippets.get(doc_id, "") for doc_id in used_ids))
    if missing:
        add("coverage_gap", "info", f"问句里的「{'、'.join(missing)}」在本轮出处里没有出现")

    # 5. 模式专属
    if ask_kind == "checklist":
        if not ("要素" in answer and "状态" in answer and "出处" in answer):
            add("checklist_missing_header", "warn", "核对清单缺少「要素 / 状态 / 出处」表头")
        for phrase in _CONCLUSION:
            if phrase in answer:
                add("checklist_conclusion", "warn", f"核对清单不应下合不合格的结论（出现「{phrase}」）")
                break
    if ask_kind == "materials":
        if not cites:
            add("materials_empty", "warn", "拿资料模式下没有返回任何资料")
        elif not any(item["images"] for item in cites):
            add("materials_no_image", "info", "这次拿资料没有带上图")

    return _finish(items, checked=6 + len(facts))


def _finish(items: list[dict], *, checked: int) -> dict:
    weight = {"error": 3, "warn": 2, "info": 1}
    failed = sum(weight.get(item["severity"], 1) for item in items)
    score = max(0.0, 1.0 - failed / max(1.0, checked * 2.0))
    if any(item["severity"] == "error" for item in items):
        status = "error"
    elif any(item["severity"] == "warn" for item in items):
        status = "warn"
    else:
        status = "ok"
    return {"status": status, "score": round(score, 3), "items": items, "checked": checked}


def _clean_citations(citations: list[dict]) -> list[dict]:
    out: list[dict] = []
    for index, raw in enumerate(citations, start=1):
        if not isinstance(raw, dict):
            continue
        try:
            doc_id = int(raw.get("id"))
        except (TypeError, ValueError):
            continue
        out.append(
            {
                "index": index,
                "id": doc_id,
                "title": str(raw.get("title") or ""),
                "images": raw.get("images") or [],
            }
        )
    return out


def _doc_map(ranked_full: list) -> dict[int, dict]:
    """把 ranked_full 收成 {资料 id: {snippet, title}}。"""

    out: dict[int, dict] = {}
    for row in ranked_full:
        if isinstance(row, tuple) and len(row) >= 3:
            document, _score, snippet = row[0], row[1], row[2]
        elif isinstance(row, dict):
            document, snippet = row.get("document") or row.get("row"), row.get("snippet", "")
        else:
            continue
        doc_id = getattr(document, "id", None)
        title = getattr(document, "title", None) or getattr(document, "file_name", None) or ""
        if doc_id is None and isinstance(document, dict):
            doc_id = document.get("id")
            title = document.get("title") or document.get("file_name") or ""
        try:
            out[int(doc_id)] = {"snippet": str(snippet or ""), "title": str(title or "")}
        except (TypeError, ValueError):
            continue
    return out


def _norm(text: str) -> str:
    return "".join((text or "").lower().split())


def _extract_facts(text: str) -> list[dict]:
    """抽日期、金额、编号、百分比、引号原文。同一种只留一份。"""

    facts: list[dict] = []
    seen: set[tuple[str, str]] = set()
    work = text or ""

    def push(kind: str, canon: str, raw: str) -> None:
        key = (kind, canon)
        if not canon or key in seen:
            return
        seen.add(key)
        facts.append({"type": kind, "canon": canon, "raw": raw.strip()})

    def mask(pattern: re.Pattern[str]) -> None:
        nonlocal work
        work = pattern.sub(lambda match: " " * len(match.group(0)), work)

    for match in _DATE_YMD.finditer(work):
        year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
        if 1 <= month <= 12 and 1 <= day <= 31:
            push("date", f"{year:04d}-{month:02d}-{day:02d}", match.group(0))
    mask(_DATE_YMD)
    for match in _DATE_YM.finditer(work):
        year, month = int(match.group(1)), int(match.group(2))
        if 1 <= month <= 12:
            push("month", f"{year:04d}-{month:02d}", match.group(0))
    mask(_DATE_YM)
    for match in _AMOUNT.finditer(work):
        canon = _amount_canon(match.group(1), match.group(2))
        if canon:
            push("amount", canon, match.group(0))
    mask(_AMOUNT)
    for match in _PERCENT.finditer(work):
        push("percent", f"{Decimal(match.group(1)).normalize():f}%", match.group(0))
    mask(_PERCENT)
    for match in _DURATION.finditer(work):
        value = Decimal(match.group(1))
        # 2025 年、2033 年这种是年份，不是期限
        if match.group(2) in {"年"} and value >= 1000:
            continue
        push("duration", f"D:{value.normalize():f}{match.group(2)}", match.group(0))
    mask(_DURATION)
    for match in _ID_TOKEN.finditer(work):
        token = match.group(0)
        if not any(ch.isdigit() for ch in token):
            continue
        if not any(ch.isalpha() for ch in token) and len(token) < 12:
            continue
        push("id", token.upper(), token)
    mask(_ID_TOKEN)
    for match in _QUOTE.finditer(work):
        quote = match.group(1).strip()
        if quote:
            push("quote", _norm(quote), quote)

    return facts


def _amount_canon(number: str, unit: str) -> str:
    try:
        value = Decimal(number.replace(",", "").replace("，", ""))
    except InvalidOperation:
        return ""
    factor = {"元": Decimal(1), "万元": Decimal(10000), "亿元": Decimal(100000000)}.get(unit, Decimal(1))
    total = value * factor
    return f"AMT:{total.normalize():f}"


def _fact_set(text: str) -> set[str]:
    return {fact["canon"] for fact in _extract_facts(text)}


def _fact_supported(fact: dict, text: str, fact_set: set[str]) -> bool:
    if fact["type"] == "quote":
        return fact["canon"] in _norm(text) or fact["canon"] in fact_set
    return fact["canon"] in fact_set


def _field_conflicts(snippets: dict[int, str], answer: str) -> str:
    """同一字段在两份资料里写法不同、回答没标冲突时给一条低置信提示。"""

    if "【冲突】" in answer:
        return ""
    groups: dict[str, dict[str, set[int]]] = {}
    for doc_id, text in snippets.items():
        for field in _FIELDS:
            start = 0
            while True:
                pos = text.find(field, start)
                if pos < 0:
                    break
                tail = text[pos : pos + 40]
                fact = next(iter(_extract_facts(tail)), None)
                if fact and fact["type"] in {"date", "month", "amount", "id", "duration"}:
                    groups.setdefault(field, {}).setdefault(fact["canon"], set()).add(doc_id)
                start = pos + len(field)
    for field, values in groups.items():
        docs = {doc_id for ids in values.values() for doc_id in ids}
        if len(values) >= 2 and len(docs) >= 2:
            samples = " / ".join(value.replace("AMT:", "") for value in list(values)[:2])
            return f"本轮资料对「{field}」有两处不同写法（{samples}），回答没有标【冲突】"
    return ""


def _coverage_gap(question: str, cited_text: str) -> list[str]:
    """问句里的实词在出处里一个都没出现时提示。只提示，不判定。"""

    if not cited_text.strip():
        return []
    haystack = _norm(cited_text)
    terms: list[str] = []
    for token in re.findall(r"[a-z0-9_]{2,}|[一-鿿]{2,}", (question or "").lower()):
        if token in _STOP_TERMS or token in terms:
            continue
        if len(token) <= 4:
            terms.append(token)
        else:
            # 长问句拆成两字词，避免「质保期多久」整串比对造成误报
            terms.extend(token[index : index + 2] for index in range(len(token) - 1))
        if len(terms) >= 10:
            break
    terms = [term for term in terms if term not in _STOP_TERMS]
    if not terms:
        return []
    missing = [term for term in terms if term not in haystack]
    if len(missing) == len(terms):
        return missing[:3]
    return []
