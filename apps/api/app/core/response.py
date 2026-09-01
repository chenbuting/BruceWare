"""统一接口返回格式。"""

from typing import Any

from fastapi.responses import JSONResponse


def ok(data: Any = None) -> dict:
    """成功。"""

    return {"ok": True, "data": data, "message": ""}


def fail(message: str, status_code: int = 400) -> JSONResponse:
    """失败。"""

    return JSONResponse(
        status_code=status_code,
        content={"ok": False, "data": None, "message": message},
    )
