"""出稿和导入时的临时进度。只放在内存里，用完即弃。"""

from __future__ import annotations

import re
import time
from threading import Lock

_JOB = re.compile(r"^[A-Za-z0-9_-]{8,40}$")
_LOCK = Lock()
_JOBS: dict[str, dict] = {}


def mark_progress(job: str, text: str, current: int, total: int) -> None:
    """记下这一步。编号不对就忽略，不影响出稿和导入本身。"""

    if not _JOB.fullmatch(job or ""):
        return
    now = time.time()
    with _LOCK:
        _JOBS[job] = {"text": text, "current": int(current), "total": int(total), "at": now}
        stale = [key for key, item in _JOBS.items() if now - float(item["at"]) > 600]
        for key in stale:
            _JOBS.pop(key, None)


def read_progress(job: str) -> dict:
    """给页面轮询。还没写上时也返回一句，避免进度条闪没。"""

    if not _JOB.fullmatch(job or ""):
        return {"text": "正在开始", "current": 0, "total": 0}
    with _LOCK:
        item = _JOBS.get(job)
    if not item:
        return {"text": "正在开始", "current": 0, "total": 0}
    return {"text": item["text"], "current": item["current"], "total": item["total"]}
