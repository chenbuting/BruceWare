"""文件柜接口：浏览、上传、下载、改名、移动、删除。"""

from __future__ import annotations

import mimetypes
from urllib.parse import quote

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel

from app.core.response import fail, ok
from app.files import store

router = APIRouter()


class NameIn(BaseModel):
    path: str = ""
    name: str = ""


class MoveIn(BaseModel):
    path: str = ""
    dest: str = ""


class PathIn(BaseModel):
    path: str = ""


def _fail_or(exc: Exception):
    return fail(str(exc) or "操作失败")


@router.get("/files/status")
def files_status():
    root, err = store.root_ready()
    return ok(
        {
            "configured": bool(store.configured_root()),
            "ready": root is not None,
            "root": str(root) if root is not None else store.configured_root(),
            "message": err,
        }
    )


@router.get("/files/list")
def list_files(path: str = ""):
    try:
        return ok(store.list_entries(path))
    except ValueError as exc:
        return _fail_or(exc)


@router.get("/files/search")
def search_files(q: str = "", path: str = ""):
    try:
        return ok(store.search_entries(q, path))
    except ValueError as exc:
        return _fail_or(exc)


@router.post("/files/mkdir")
def make_dir(body: NameIn):
    name = (body.name or "").strip()
    if not name:
        return fail("请填写文件夹名")
    try:
        return ok(store.make_dir(body.path, name))
    except ValueError as exc:
        return _fail_or(exc)


@router.post("/files/upload")
async def upload_files(path: str = Form(""), files: list[UploadFile] = File(...)):
    created = []
    try:
        for item in files:
            raw = await item.read()
            if not raw:
                continue
            created.append(store.save_upload(path, item.filename or "未命名", raw))
    except ValueError as exc:
        return _fail_or(exc)
    if not created:
        return fail("请先选文件")
    return ok({"items": created})


@router.post("/files/rename")
def rename_file(body: NameIn):
    name = (body.name or "").strip()
    if not name:
        return fail("请填写新名字")
    try:
        return ok(store.rename_entry(body.path, name))
    except ValueError as exc:
        return _fail_or(exc)


@router.post("/files/move")
def move_file(body: MoveIn):
    try:
        return ok(store.move_entry(body.path, body.dest))
    except ValueError as exc:
        return _fail_or(exc)


@router.post("/files/open")
def open_file(body: PathIn):
    if not (body.path or "").strip():
        return fail("请先选一项")
    try:
        store.open_with_system(body.path)
    except ValueError as exc:
        return _fail_or(exc)
    return ok(True)


@router.post("/files/delete")
def delete_file(body: PathIn):
    if not (body.path or "").strip():
        return fail("请先选一项")
    try:
        store.delete_entry(body.path)
    except ValueError as exc:
        return _fail_or(exc)
    return ok(True)


def _file_or_fail(path: str, download: bool):
    try:
        target = store.resolve_inside(path)
    except ValueError as exc:
        return fail(str(exc))
    if not target.is_file():
        return fail("没有这个文件")
    media = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    if target.suffix.lower() == ".pdf":
        media = "application/pdf"
    headers = {}
    if download:
        headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(target.name)}"
        return FileResponse(target, filename=target.name, media_type=media, headers=headers)
    headers["Content-Disposition"] = "inline"
    return FileResponse(target, media_type=media, headers=headers)


@router.get("/files/download")
def download_file(path: str = ""):
    return _file_or_fail(path, True)


@router.get("/files/raw")
def raw_file(path: str = ""):
    return _file_or_fail(path, False)


@router.get("/files/text")
def text_file(path: str = ""):
    try:
        target = store.resolve_inside(path)
    except ValueError as exc:
        return fail(str(exc))
    if not target.is_file():
        return fail("没有这个文件")
    if store.preview_kind(target.name) != "text":
        return fail("这个文件不能当文本打开")
    try:
        text = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = target.read_text(encoding="gbk", errors="replace")
    return PlainTextResponse(text[:200_000])
