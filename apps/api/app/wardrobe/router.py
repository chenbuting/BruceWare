"""衣橱：识别、抠图、试穿、搭配。"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ai import image_edit, image_generate
from app.core.response import fail, ok
from app.db.session import get_db
from app.wardrobe.models import WardrobeItem, WardrobeLook, WardrobeStyle
from app.wardrobe.store import (
    item_dir,
    list_style_files,
    look_dir,
    read_item_file,
    read_style_file,
    reference_path,
    style_dir,
    tmp_dir,
    write_bytes,
)
from app.wardrobe.vision import analyze_photo, crop_box, remove_chroma, to_png

router = APIRouter()
PART_LABELS = {
    "upperbody": "上装",
    "wholebody_up": "外套",
    "lowerbody": "下装",
    "accessories_up": "配饰",
    "shoes": "鞋",
}


class DetectedIn(BaseModel):
    name: str = ""
    part: str = "upperbody"
    color: str = ""
    secondaryColor: str = ""
    tags: list[str] = Field(default_factory=list)
    boundingBox: dict[str, int] = Field(default_factory=dict)


class ImportIn(BaseModel):
    upload_id: str
    items: list[DetectedIn]


class LookIn(BaseModel):
    item_ids: list[int]
    title: str = ""


class StyleActiveIn(BaseModel):
    active: bool = True


def _file_url(path: Path, url: str) -> str:
    """有文件才给地址，并带修改时间，避免换图后浏览器还显示旧的。"""
    if not path.is_file():
        return ""
    return f"{url}?v={int(path.stat().st_mtime)}"


def _item_dict(row: WardrobeItem) -> dict[str, Any]:
    folder = item_dir(row.id)
    return {
        "id": row.id,
        "name": row.name or "",
        "part": row.part or "upperbody",
        "part_label": PART_LABELS.get(row.part or "", "上装"),
        "color": row.color or "",
        "secondary_color": row.secondary_color or "",
        "tags": json.loads(row.tags or "[]"),
        "source_name": row.source_name or "",
        "has_cutout": (folder / "cutout.png").is_file(),
        "has_modeled": (folder / "modeled.png").is_file(),
        "cutout_url": _file_url(folder / "cutout.png", f"/api/v1/wardrobe/files/items/{row.id}/cutout.png"),
        "modeled_url": _file_url(folder / "modeled.png", f"/api/v1/wardrobe/files/items/{row.id}/modeled.png"),
        "original_url": _file_url(folder / "original.png", f"/api/v1/wardrobe/files/items/{row.id}/original.png"),
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }


def _look_dict(row: WardrobeLook) -> dict[str, Any]:
    path = look_dir(row.id) / "look.png"
    return {
        "id": row.id,
        "title": row.title or "",
        "item_ids": json.loads(row.item_ids or "[]"),
        "image_url": _file_url(path, f"/api/v1/wardrobe/files/looks/{row.id}/look.png"),
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }


def _garment_prompt(item: dict[str, Any]) -> str:
    name = item.get("name") or "衣服"
    part = PART_LABELS.get(item.get("part") or "", "衣服")
    color = item.get("color") or "原图颜色"
    tags = "、".join(item.get("tags") or []) or "可见的面料和细节"
    return (
        f"根据参考图，只重建这一件完整的{name}（{part}）。"
        f"去掉人、皮肤、头发、衣架、其它衣服和背景。"
        f"保留原图颜色 {color}、版型、面料和细节（{tags}），不要编造 logo 或口袋。"
        "正面产品图，衣服完整、四周留白。"
        "背景必须是均匀纯色 #00ff00，不要阴影和地面。"
    )


def _style_line(name: str) -> str:
    if not name:
        return ""
    return f"整体气质、场景和光线要像{name}的品牌风格参考图，不要复制参考图里的人脸和衣服。"


def _modeled_prompt(item: dict[str, Any], style_name: str = "") -> str:
    name = item.get("name") or "这件衣服"
    extra = _style_line(style_name)
    return (
        "用第一张图的人，穿上第二张图那件衣服，拍一张真实的时尚照片。"
        f"人脸、发型、年龄、身材要像第一张；衣服要完全是第二张这件{name}，颜色和细节不能改。"
        f"{extra}"
        "衣服要完整露出来，配简单的其它衣服，自然光，真实场景。不要文字、水印。"
    )


def _outfit_prompt(names: list[str], style_name: str = "") -> str:
    joined = "、".join(names)
    extra = _style_line(style_name)
    return (
        "用第一张图的人，穿上后面几张图里的衣服，拍一套完整造型。"
        f"衣服是：{joined}。人脸要像第一张，衣服颜色和细节按参考图，不要乱改。"
        f"{extra}"
        "全身能看清搭配，真实场景，自然光。不要文字、水印。"
    )


def _style_dict(row: WardrobeStyle) -> dict[str, Any]:
    files = list_style_files(row.id)
    return {
        "id": row.id,
        "name": row.name or "",
        "active": bool(row.active),
        "image_urls": [
            _file_url(path, f"/api/v1/wardrobe/files/styles/{row.id}/{path.name}") for path in files
        ],
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }


def _active_style(db: Session) -> WardrobeStyle | None:
    return db.scalars(select(WardrobeStyle).where(WardrobeStyle.active == 1)).first()


def _style_refs(db: Session) -> tuple[str, list[bytes]]:
    row = _active_style(db)
    if row is None:
        return "", []
    files = list_style_files(row.id)[:2]
    return row.name or "", [path.read_bytes() for path in files]


@router.get("/wardrobe/status")
def wardrobe_status(db: Session = Depends(get_db)):
    ref = reference_path()
    style = _active_style(db)
    return ok(
        {
            "has_reference": ref.is_file(),
            "reference_url": _file_url(ref, "/api/v1/wardrobe/files/reference/model-reference.png"),
            "active_style_id": style.id if style else 0,
            "active_style_name": style.name if style else "",
        }
    )


@router.post("/wardrobe/reference")
async def save_reference(file: UploadFile = File(...)):
    raw = await file.read()
    if not raw:
        return fail("请选一张自己的照片")
    write_bytes(reference_path(), raw)
    return ok({"has_reference": True, "reference_url": _file_url(reference_path(), "/api/v1/wardrobe/files/reference/model-reference.png")})


@router.get("/wardrobe/items")
def list_items(db: Session = Depends(get_db)):
    rows = db.scalars(select(WardrobeItem).order_by(WardrobeItem.id.desc())).all()
    return ok({"items": [_item_dict(row) for row in rows]})


@router.post("/wardrobe/items")
async def add_item(
    file: UploadFile = File(...),
    name: str = Form(""),
    part: str = Form("upperbody"),
    db: Session = Depends(get_db),
):
    """已经是单件图时，不走识别，直接放进衣橱。"""
    raw = await file.read()
    if not raw:
        return fail("请选一张衣服图片")
    try:
        picture = to_png(raw)
    except Exception:
        return fail("这张图打不开")
    row = WardrobeItem(
        name=(name.strip() or (file.filename or "衣服").rsplit(".", 1)[0])[:200] or "衣服",
        part=part if part in PART_LABELS else "upperbody",
        color="",
        secondary_color="",
        tags="[]",
        source_name=file.filename or "",
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.flush()
    folder = item_dir(row.id)
    write_bytes(folder / "original.png", picture)
    write_bytes(folder / "cutout.png", picture)
    db.commit()
    db.refresh(row)
    return ok(_item_dict(row))


@router.delete("/wardrobe/items/{item_id}")
def delete_item(item_id: int, db: Session = Depends(get_db)):
    row = db.get(WardrobeItem, item_id)
    if row is None:
        return fail("没有这件衣服")
    folder = item_dir(item_id)
    for child in folder.glob("*"):
        child.unlink()
    db.delete(row)
    db.commit()
    return ok(True)


@router.post("/wardrobe/analyze")
async def analyze(file: UploadFile = File(...)):
    raw = await file.read()
    if not raw:
        return fail("请上传照片")
    upload_id = uuid.uuid4().hex
    path = tmp_dir() / f"{upload_id}.bin"
    write_bytes(path, raw)
    try:
        items = analyze_photo(raw, file.content_type or "image/jpeg")
    except ValueError as exc:
        return fail(str(exc))
    except Exception:
        return fail("这张照片识别失败")
    return ok({"upload_id": upload_id, "source_name": file.filename or "", "items": items})


@router.post("/wardrobe/import")
def import_items(body: ImportIn, db: Session = Depends(get_db)):
    source = tmp_dir() / f"{body.upload_id}.bin"
    if not source.is_file():
        return fail("原图已经过期，请重新识别")
    raw = source.read_bytes()
    created: list[dict[str, Any]] = []
    for item in body.items:
        data = item.model_dump()
        row = WardrobeItem(
            name=data["name"][:200] or "衣服",
            part=data["part"] if data["part"] in PART_LABELS else "upperbody",
            color=data.get("color") or "",
            secondary_color=data.get("secondaryColor") or "",
            tags=json.dumps(data.get("tags") or [], ensure_ascii=False),
            source_name=body.upload_id,
            created_at=datetime.utcnow(),
        )
        db.add(row)
        db.flush()
        folder = item_dir(row.id)
        write_bytes(folder / "original.png", raw)
        crop = crop_box(raw, data.get("boundingBox") or {})
        try:
            cutout = image_edit(_garment_prompt(data), [crop])
            cutout = remove_chroma(cutout)
        except ValueError:
            try:
                cutout = image_generate(_garment_prompt(data))
                cutout = remove_chroma(cutout)
            except ValueError as exc:
                db.rollback()
                return fail(str(exc))
        write_bytes(folder / "cutout.png", cutout)
        created.append(_item_dict(row))
    db.commit()
    try:
        source.unlink()
    except Exception:
        pass
    return ok({"items": created})


@router.post("/wardrobe/items/{item_id}/modeled")
def remake_modeled(item_id: int, db: Session = Depends(get_db)):
    row = db.get(WardrobeItem, item_id)
    if row is None:
        return fail("没有这件衣服")
    ref = reference_path()
    cutout = item_dir(item_id) / "cutout.png"
    if not ref.is_file():
        return fail("请先上传一张自己的照片")
    if not cutout.is_file():
        return fail("还没有单件图")
    try:
        modeled = image_edit(
            _modeled_prompt({"name": row.name}),
            [ref.read_bytes(), cutout.read_bytes()],
            size="1536x1024",
        )
    except ValueError:
        try:
            modeled = image_edit(_modeled_prompt({"name": row.name}), [ref.read_bytes(), cutout.read_bytes()])
        except ValueError as exc:
            return fail(str(exc))
    write_bytes(item_dir(item_id) / "modeled.png", modeled)
    return ok(_item_dict(row))


@router.get("/wardrobe/looks")
def list_looks(db: Session = Depends(get_db)):
    rows = db.scalars(select(WardrobeLook).order_by(WardrobeLook.id.desc())).all()
    return ok({"items": [_look_dict(row) for row in rows]})


@router.post("/wardrobe/looks")
def make_look(body: LookIn, db: Session = Depends(get_db)):
    ids = [int(item) for item in body.item_ids if item]
    if len(ids) < 1:
        return fail("请先选一件衣服")
    ref = reference_path()
    if not ref.is_file():
        return fail("请先上传一张自己的照片")
    rows = [db.get(WardrobeItem, item_id) for item_id in ids]
    if any(row is None for row in rows):
        return fail("有衣服找不到了")
    style_name, style_bytes = _style_refs(db)
    images = [ref.read_bytes()]
    names = []
    clothes_limit = 3 if style_bytes else 4
    for row in rows[:clothes_limit]:
        cutout = item_dir(row.id) / "cutout.png"
        if not cutout.is_file():
            return fail(f"{row.name} 还没有单件图")
        images.append(cutout.read_bytes())
        names.append(row.name)
    images.extend(style_bytes)
    prompt = _modeled_prompt({"name": names[0]}, style_name) if len(names) == 1 else _outfit_prompt(names, style_name)
    try:
        picture = image_edit(prompt, images[:5], size="1536x1024")
    except ValueError:
        try:
            picture = image_edit(prompt, images[:5])
        except ValueError as exc:
            return fail(str(exc))
    title = body.title.strip() or "、".join(names)
    if style_name and style_name not in title:
        title = f"{title} · {style_name}"
    row = WardrobeLook(
        title=title[:200],
        item_ids=json.dumps(ids),
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.flush()
    write_bytes(look_dir(row.id) / "look.png", picture)
    db.commit()
    db.refresh(row)
    return ok(_look_dict(row))


@router.get("/wardrobe/styles")
def list_styles(db: Session = Depends(get_db)):
    rows = db.scalars(select(WardrobeStyle).order_by(WardrobeStyle.id.desc())).all()
    active = _active_style(db)
    return ok({"items": [_style_dict(row) for row in rows], "active_id": active.id if active else 0})


@router.post("/wardrobe/styles")
async def add_style(
    name: str = Form(""),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    title = name.strip() or "未命名风格"
    pictures: list[bytes] = []
    for item in files[:4]:
        raw = await item.read()
        if not raw:
            continue
        try:
            pictures.append(to_png(raw))
        except Exception:
            return fail("有一张风格图打不开")
    if not pictures:
        return fail("请上传至少一张品牌图")
    has_active = _active_style(db) is not None
    row = WardrobeStyle(name=title[:200], active=0 if has_active else 1, created_at=datetime.utcnow())
    db.add(row)
    db.flush()
    for index, picture in enumerate(pictures, start=1):
        write_bytes(style_dir(row.id) / f"{index}.png", picture)
    db.commit()
    db.refresh(row)
    return ok(_style_dict(row))


@router.put("/wardrobe/styles/{style_id}/active")
def set_style_active(style_id: int, body: StyleActiveIn, db: Session = Depends(get_db)):
    row = db.get(WardrobeStyle, style_id)
    if row is None:
        return fail("没有这个风格")
    for item in db.scalars(select(WardrobeStyle)).all():
        item.active = 0
    row.active = 1 if body.active else 0
    db.commit()
    rows = db.scalars(select(WardrobeStyle).order_by(WardrobeStyle.id.desc())).all()
    return ok({"items": [_style_dict(item) for item in rows], "active_id": row.id if body.active else 0})


@router.delete("/wardrobe/styles/{style_id}")
def delete_style(style_id: int, db: Session = Depends(get_db)):
    row = db.get(WardrobeStyle, style_id)
    if row is None:
        return fail("没有这个风格")
    folder = style_dir(style_id)
    for child in folder.glob("*"):
        child.unlink()
    db.delete(row)
    db.commit()
    return ok(True)


@router.delete("/wardrobe/looks/{look_id}")
def delete_look(look_id: int, db: Session = Depends(get_db)):
    row = db.get(WardrobeLook, look_id)
    if row is None:
        return fail("没有这套搭配")
    path = look_dir(look_id) / "look.png"
    if path.is_file():
        path.unlink()
    db.delete(row)
    db.commit()
    return ok(True)


@router.get("/wardrobe/files/reference/{name}")
def file_reference(name: str):
    if name != "model-reference.png":
        return fail("没有这个文件")
    path = reference_path()
    if not path.is_file():
        return fail("还没有参考照片")
    return FileResponse(path)


@router.get("/wardrobe/files/items/{item_id}/{name}")
def file_item(item_id: int, name: str):
    path = read_item_file(item_id, name)
    if path is None:
        return fail("没有这张图")
    return FileResponse(path)


@router.get("/wardrobe/files/looks/{look_id}/{name}")
def file_look(look_id: int, name: str):
    if name != "look.png":
        return fail("没有这张图")
    path = look_dir(look_id) / name
    if not path.is_file():
        return fail("没有这张图")
    return FileResponse(path)


@router.get("/wardrobe/files/styles/{style_id}/{name}")
def file_style(style_id: int, name: str):
    path = read_style_file(style_id, name)
    if path is None:
        return fail("没有这张图")
    return FileResponse(path)
