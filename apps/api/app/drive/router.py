"""网盘接口：账号、授权、浏览和文件操作。"""

from __future__ import annotations

import mimetypes
import tempfile
import time
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.core.response import fail, ok
from app.drive.adapters import get_adapter
from app.drive.kinds import kind_ready, list_kinds
from app.drive.store import delete_raw, get_raw, list_raw, new_id, public_account, save_raw

router = APIRouter()
_pending: dict[str, str] = {}
_CALLBACK = "http://127.0.0.1:8000/api/v1/drive/baidu/callback"


class AccountIn(BaseModel):
    kind: str = "baidu"
    name: str = Field(default="", max_length=80)
    app_key: str = Field(default="", max_length=200)
    secret_key: str = Field(default="", max_length=200)
    app_name: str = Field(default="", max_length=80)


class PathIn(BaseModel):
    path: str = ""
    name: str = ""
    dest: str = ""
    fsid: int = 0
    paths: list[str] = Field(default_factory=list)


def _account_or_fail(account_id: str):
    row = get_raw(account_id)
    if row is None:
        return None, fail("这个账号不存在", 404)
    return row, None


def _adapter(row: dict):
    return get_adapter(str(row.get("kind") or ""))


def _save_tokens(row: dict) -> dict:
    return save_raw(row)


def _body_paths(body: PathIn) -> list[str]:
    items = [item.strip() for item in body.paths if item and item.strip()]
    if not items and body.path.strip():
        items = [body.path.strip()]
    return items


def _refresh_if_needed(row: dict) -> dict:
    """令牌快过期时先静默刷新，失败就留给页面提示重新授权。"""

    expires = int(row.get("expires_at") or 0)
    if not row.get("refresh_token"):
        return row
    if expires and expires > time.time() + 600:
        return row
    if not expires:
        return row
    try:
        adapter = _adapter(row)
        tokens = adapter.refresh(row)
        adapter.apply_tokens(row, tokens)
        return _save_tokens(row)
    except ValueError:
        return row


@router.get("/drive/kinds")
def drive_kinds():
    """列出已接和预留的网盘种类。"""

    return ok({"items": list_kinds()})


@router.get("/drive/accounts")
def list_accounts():
    items = []
    for row in list_raw():
        items.append(public_account(_refresh_if_needed(row)))
    return ok({"items": items})


@router.post("/drive/accounts")
def create_account(body: AccountIn):
    kind = (body.kind or "baidu").strip()
    if not kind_ready(kind):
        return fail("这种网盘以后再接")
    if not body.app_key.strip() or not body.secret_key.strip():
        return fail("请填写 AppKey 和 SecretKey")
    row = {
        "id": new_id(),
        "kind": kind,
        "name": body.name.strip() or "百度网盘",
        "app_key": body.app_key.strip(),
        "secret_key": body.secret_key.strip(),
        "app_name": body.app_name.strip(),
        "access_token": "",
        "refresh_token": "",
        "expires_at": 0,
        "user_label": "",
    }
    save_raw(row)
    return ok(public_account(row))


@router.put("/drive/accounts/{account_id}")
def update_account(account_id: str, body: AccountIn):
    row, err = _account_or_fail(account_id)
    if err is not None:
        return err
    row["name"] = body.name.strip() or row.get("name") or "百度网盘"
    if body.app_key.strip():
        row["app_key"] = body.app_key.strip()
    if body.secret_key.strip():
        row["secret_key"] = body.secret_key.strip()
    row["app_name"] = body.app_name.strip()
    save_raw(row)
    return ok(public_account(row))


@router.delete("/drive/accounts/{account_id}")
def remove_account(account_id: str):
    if not delete_raw(account_id):
        return fail("这个账号不存在", 404)
    _pending.pop(account_id, None)
    return ok(True)


@router.post("/drive/accounts/{account_id}/auth/start")
def start_auth(account_id: str):
    """向百度要设备码，页面上显示给用户去授权。"""

    row, err = _account_or_fail(account_id)
    if err is not None:
        return err
    try:
        adapter = _adapter(row)
        data = adapter.start_auth(row)
    except ValueError as exc:
        return fail(str(exc))
    _pending[account_id] = str(data.get("device_code") or "")
    return ok(
        {
            "user_code": data.get("user_code") or "",
            "verify_url": data.get("verify_url") or "",
            "qrcode_url": data.get("qrcode_url") or "",
            "auth_url": adapter.auth_url(row, _CALLBACK),
            "interval": data.get("interval") or 5,
        }
    )


@router.post("/drive/accounts/{account_id}/auth/poll")
def poll_auth(account_id: str):
    row, err = _account_or_fail(account_id)
    if err is not None:
        return err
    device_code = _pending.get(account_id) or ""
    if not device_code:
        return fail("请先点授权")
    try:
        adapter = _adapter(row)
        tokens = adapter.poll_auth(row, device_code)
        if tokens is None:
            return ok({"done": False, **public_account(row)})
        adapter.apply_tokens(row, tokens)
        _save_tokens(row)
        _pending.pop(account_id, None)
        return ok({"done": True, **public_account(row)})
    except ValueError as exc:
        return fail(str(exc))


@router.get("/drive/baidu/callback")
def baidu_callback(code: str = "", state: str = ""):
    """浏览器授权后百度跳回来。"""

    if not code or not state:
        return HTMLResponse("<p>授权没完成，请回到网盘重新点授权。</p>", status_code=400)
    row = get_raw(state)
    if row is None:
        return HTMLResponse("<p>找不到这个账号。</p>", status_code=404)
    try:
        adapter = _adapter(row)
        tokens = adapter.finish_code(row, code, _CALLBACK)
        adapter.apply_tokens(row, tokens)
        _save_tokens(row)
        _pending.pop(state, None)
    except ValueError as exc:
        return HTMLResponse(f"<p>{exc}</p>", status_code=400)
    return HTMLResponse("<p>授权成功，可以关掉这页，回到网盘。</p>")


@router.get("/drive/accounts/{account_id}/quota")
def account_quota(account_id: str):
    """查这个账号的已用空间。"""

    row, err = _account_or_fail(account_id)
    if err is not None:
        return err
    adapter = _adapter(row)
    getter = getattr(adapter, "quota", None)
    if getter is None:
        return fail("这种网盘还不能查容量")
    try:
        data = getter(row)
        return ok(data)
    except ValueError as exc:
        return fail(str(exc))
    finally:
        _save_tokens(row)


@router.get("/drive/accounts/{account_id}/list")
def list_files(account_id: str, path: str = ""):
    row, err = _account_or_fail(account_id)
    if err is not None:
        return err
    try:
        data = _adapter(row).list_dir(row, path)
        return ok(data)
    except ValueError as exc:
        return fail(str(exc))
    finally:
        _save_tokens(row)


@router.get("/drive/accounts/{account_id}/search")
def search_files(account_id: str, q: str = "", path: str = ""):
    if not q.strip():
        return fail("请填写要找的字")
    row, err = _account_or_fail(account_id)
    if err is not None:
        return err
    try:
        data = _adapter(row).search(row, q, path)
        return ok(data)
    except ValueError as exc:
        return fail(str(exc))
    finally:
        _save_tokens(row)


@router.post("/drive/accounts/{account_id}/mkdir")
def make_dir(account_id: str, body: PathIn):
    row, err = _account_or_fail(account_id)
    if err is not None:
        return err
    name = (body.name or "").strip()
    if not name:
        return fail("请填写文件夹名")
    try:
        item = _adapter(row).mkdir(row, body.path, name)
        _save_tokens(row)
        return ok(item)
    except ValueError as exc:
        return fail(str(exc))


@router.post("/drive/accounts/{account_id}/upload")
async def upload_file(account_id: str, path: str = Form(""), files: list[UploadFile] = File(...)):
    row, err = _account_or_fail(account_id)
    if err is not None:
        return err
    created = []
    try:
        adapter = _adapter(row)
        for item in files:
            tmp_path = ""
            try:
                with tempfile.NamedTemporaryFile(delete=False) as tmp:
                    tmp_path = tmp.name
                    while True:
                        piece = await item.read(4 * 1024 * 1024)
                        if not piece:
                            break
                        tmp.write(piece)
                created.append(adapter.upload(row, path, item.filename or "未命名", tmp_path))
            finally:
                if tmp_path:
                    Path(tmp_path).unlink(missing_ok=True)
        _save_tokens(row)
        return ok({"items": created})
    except ValueError as exc:
        return fail(str(exc))


@router.post("/drive/accounts/{account_id}/rename")
def rename_file(account_id: str, body: PathIn):
    row, err = _account_or_fail(account_id)
    if err is not None:
        return err
    if not body.name.strip():
        return fail("请填写新名字")
    try:
        item = _adapter(row).rename(row, body.path, body.name)
        _save_tokens(row)
        return ok(item)
    except ValueError as exc:
        return fail(str(exc))


@router.post("/drive/accounts/{account_id}/move")
def move_file(account_id: str, body: PathIn):
    row, err = _account_or_fail(account_id)
    if err is not None:
        return err
    paths = _body_paths(body)
    if not paths:
        return fail("请先选文件")
    try:
        items = _adapter(row).relocate(row, paths, body.dest, "move")
        _save_tokens(row)
        return ok({"items": items})
    except ValueError as exc:
        return fail(str(exc))


@router.post("/drive/accounts/{account_id}/copy")
def copy_file(account_id: str, body: PathIn):
    row, err = _account_or_fail(account_id)
    if err is not None:
        return err
    paths = _body_paths(body)
    if not paths:
        return fail("请先选文件")
    try:
        items = _adapter(row).relocate(row, paths, body.dest, "copy")
        _save_tokens(row)
        return ok({"items": items})
    except ValueError as exc:
        return fail(str(exc))


@router.post("/drive/accounts/{account_id}/delete")
def delete_file(account_id: str, body: PathIn):
    row, err = _account_or_fail(account_id)
    if err is not None:
        return err
    paths = _body_paths(body)
    if not paths:
        return fail("请先选文件")
    try:
        _adapter(row).delete_many(row, paths)
        _save_tokens(row)
        return ok(True)
    except ValueError as exc:
        return fail(str(exc))


@router.get("/drive/accounts/{account_id}/download")
def download_file(account_id: str, path: str = "", fsid: int = 0):
    return _stream_file(account_id, path, fsid, True)


@router.get("/drive/accounts/{account_id}/raw")
def raw_file(account_id: str, path: str = "", fsid: int = 0):
    """给页面预览用，不当成附件下载。"""

    return _stream_file(account_id, path, fsid, False)


def _stream_file(account_id: str, path: str, fsid: int, as_download: bool):
    row, err = _account_or_fail(account_id)
    if err is not None:
        return err
    try:
        name, response, client = _adapter(row).open_download(row, path, fsid)
        _save_tokens(row)
    except ValueError as exc:
        return fail(str(exc))

    def chunks():
        try:
            for chunk in response.iter_bytes():
                yield chunk
        finally:
            response.close()
            client.close()

    media = mimetypes.guess_type(name)[0] or "application/octet-stream"
    if name.lower().endswith(".pdf"):
        media = "application/pdf"
    mode = "attachment" if as_download else "inline"
    return StreamingResponse(
        chunks(),
        media_type=media,
        headers={"Content-Disposition": f"{mode}; filename*=UTF-8''{quote(name)}"},
    )
