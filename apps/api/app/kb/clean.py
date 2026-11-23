"""知识库清洗：默认收成一行。勾上的做法按顺序做，自定义规则和脚本最后做。"""

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
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
    script: str = "",
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
    if rules:
        rule_passed, rule_blocked, body = _apply_rules(body, rules)
        add("自定义规则", rule_passed, rule_blocked)
    source = (script or "").strip()
    if source:
        before = body
        body = _run_script(before, source)
        add("处理脚本", 0 if body != before else 1, 1 if body != before else 0)
    if limit is not None:
        body = body[:limit]
    order = ["完整性", "唯一性", "规范性", "有效性", "安全性", "自定义规则", "处理脚本"]
    return body, [scores[name] for name in order if name in scores]


class CleanScriptError(ValueError):
    """自定义规则或脚本没做成。正文先不改。"""


def _apply_rules(body: str, rules: list[dict]) -> tuple[int, int, str]:
    """按怎么认、怎么处理来改。返回过了几条、挡了几条和新正文。"""

    passed = blocked = 0
    for rule in rules:
        find = str(rule.get("find") or "")
        if not find:
            continue
        how = str(rule.get("how") or "contains")
        action = str(rule.get("action") or "replace")
        repl = "" if action == "cut" else str(rule.get("replace") or "")
        pattern = _compile_rule(how, find)
        if action in {"drop_line", "keep_line"}:
            lines = body.splitlines()
            kept: list[str] = []
            for line in lines:
                hit = _line_hit(line, how, find, pattern)
                stay = hit if action == "keep_line" else not hit
                if stay:
                    kept.append(line)
                    passed += 1
                else:
                    blocked += 1
            body = "\n".join(kept)
            continue
        if how == "regex" and pattern is not None:
            try:
                body, count = pattern.subn(repl, body)
            except re.error as exc:
                raise CleanScriptError(f"这条正则写错了：{exc}") from exc
            blocked += count
            passed += 0 if count else 1
            continue
        if how in {"start", "end"}:
            lines = body.splitlines()
            changed: list[str] = []
            for line in lines:
                nxt, count = _edge_replace(line, how, find, repl)
                if count:
                    blocked += count
                else:
                    passed += 1
                changed.append(nxt)
            body = "\n".join(changed)
            continue
        count = body.count(find)
        if count:
            blocked += count
            body = body.replace(find, repl)
        else:
            passed += 1
    return passed, blocked, body


def _compile_rule(how: str, find: str) -> re.Pattern[str] | None:
    if how != "regex":
        return None
    try:
        return re.compile(find)
    except re.error as exc:
        raise CleanScriptError(f"这条正则写错了：{exc}") from exc


def _line_hit(line: str, how: str, find: str, pattern: re.Pattern[str] | None) -> bool:
    if how == "start":
        return line.startswith(find)
    if how == "end":
        return line.rstrip().endswith(find)
    if how == "regex":
        return bool(pattern.search(line)) if pattern else False
    return find in line


def _edge_replace(line: str, how: str, find: str, repl: str) -> tuple[str, int]:
    if how == "start" and line.startswith(find):
        return repl + line[len(find) :], 1
    if how == "end" and line.rstrip().endswith(find):
        core = line.rstrip()
        tail = line[len(core) :]
        return core[: len(core) - len(find)] + repl + tail, 1
    return line, 0


# 脚本只能改 text。不给读文件、不给导入别的库。
_SAFE_BUILTINS = {
    "len": len,
    "range": range,
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list": list,
    "dict": dict,
    "set": set,
    "tuple": tuple,
    "min": min,
    "max": max,
    "sum": sum,
    "abs": abs,
    "round": round,
    "enumerate": enumerate,
    "zip": zip,
    "map": map,
    "filter": filter,
    "sorted": sorted,
    "reversed": reversed,
    "any": any,
    "all": all,
    "True": True,
    "False": False,
    "None": None,
}


def _run_script(text: str, source: str) -> str:
    """跑用户写的处理脚本。text 改完必须还是一段文字。"""

    def work() -> str:
        env: dict = {"text": text, "re": re, "__builtins__": _SAFE_BUILTINS}
        exec(source, env, env)
        result = env.get("text")
        if not isinstance(result, str):
            raise CleanScriptError("脚本要把结果放回 text，而且必须是一段文字")
        return result

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(work).result(timeout=3)
    except CleanScriptError:
        raise
    except FuturesTimeout as exc:
        raise CleanScriptError("脚本跑太久，已停掉") from exc
    except Exception as exc:
        raise CleanScriptError(f"脚本没跑成：{exc}") from exc


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
