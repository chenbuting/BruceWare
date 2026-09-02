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
    copy_look_style,
    copy_style_into_look,
    item_dir,
    list_look_style_files,
    list_style_files,
    look_dir,
    look_image_opts,
    look_prompt,
    look_style_name,
    save_look_image_opts,
    save_look_prompt,
    read_item_file,
    read_look_file,
    read_style_file,
    reference_path,
    style_dir,
    tmp_dir,
    write_bytes,
)
from app.wardrobe.vision import analyze_photo, crop_box, describe_style, remove_chroma, suggest_outfits, to_png

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


class ItemPatchIn(BaseModel):
    part: str = ""
    name: str = ""


class LookIn(BaseModel):
    item_ids: list[int]
    title: str = ""
    ratio: str = ""
    quality: str = ""


class LookPromptIn(BaseModel):
    prompt: str = ""
    ratio: str = ""
    quality: str = ""


class SceneIn(BaseModel):
    look_id: int = 0
    scene: str = ""
    ratio: str = ""
    quality: str = ""


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
    before = look_dir(row.id) / "source.png"
    style_files = list_look_style_files(row.id)
    name = look_style_name(row.id, row.title or "")
    opts = look_image_opts(row.id)
    return {
        "id": row.id,
        "title": row.title or "",
        "item_ids": json.loads(row.item_ids or "[]"),
        "image_url": _file_url(path, f"/api/v1/wardrobe/files/looks/{row.id}/look.png"),
        "source_image_url": _file_url(before, f"/api/v1/wardrobe/files/looks/{row.id}/source.png"),
        "prompt": look_prompt(row.id),
        "style_name": name,
        "style_image_urls": [
            _file_url(item, f"/api/v1/wardrobe/files/looks/{row.id}/{item.name}") for item in style_files
        ],
        "image_ratio": opts["ratio"],
        "image_quality": opts["quality"],
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }


RATIO_SIZES = {
    "1:1": ["1024x1024"],
    "3:4": ["1024x1536", "1024x1024"],
    "2:3": ["1024x1536", "1024x1024"],
    "9:16": ["1024x1792", "1024x1536", "1024x1024"],
    "4:3": ["1536x1024", "1024x1024"],
    "3:2": ["1536x1024", "1024x1024"],
    "16:9": ["1792x1024", "1536x1024", "1024x1024"],
}
QUALITY_VALUES = {
    "standard": ["medium", "standard"],
    "high": ["high", "hd"],
    "low": ["low"],
}


def _normalize_image_opts(ratio: str, quality: str) -> tuple[str, str, list[str], list[str]]:
    """把用户选的比例、质量收成接口能认的值。"""

    ratio = (ratio or "3:4").strip()
    if ratio not in RATIO_SIZES:
        ratio = "3:4"
    quality = (quality or "standard").strip()
    if quality not in QUALITY_VALUES:
        quality = "standard"
    return ratio, quality, RATIO_SIZES[ratio], QUALITY_VALUES[quality]


def _resolve_image_opts(ratio: str, quality: str, look_id: int = 0) -> tuple[str, str, list[str], list[str]]:
    """改旧图时沿用上次的比例和质量，新图用当前选择。"""

    saved = look_image_opts(look_id) if look_id else {"ratio": "", "quality": ""}
    return _normalize_image_opts(ratio or saved["ratio"], quality or saved["quality"])


def _edit_look(prompt: str, images: list[bytes], ratio: str = "", quality: str = "", look_id: int = 0) -> tuple[bytes, str, str]:
    """按选定或上次记下的比例、质量出图。"""

    ratio, quality, sizes, qualities = _resolve_image_opts(ratio, quality, look_id)
    picture = image_edit(prompt, images, size=sizes[0], timeout=180, sizes=sizes, qualities=qualities)
    return picture, ratio, quality


def _backfill_look_style(row: WardrobeLook, db: Session) -> None:
    """旧搭配还没存风格图时，按标题补一份，补完就不再跟着风格库变。"""

    if list_look_style_files(row.id):
        return
    title = row.title or ""
    matched = [item for item in db.scalars(select(WardrobeStyle)).all() if item.name and title.endswith(f" · {item.name}")]
    if not matched:
        return
    matched.sort(key=lambda item: item.id)
    copy_style_into_look(row.id, matched[0].id, matched[0].name or "")


def _backfill_look_source(row: WardrobeLook, db: Session) -> None:
    """旧裂变图补上原图，方便点开对比。"""

    folder = look_dir(row.id)
    if (folder / "source.png").is_file():
        return
    title = row.title or ""
    if "姿势裂变" not in title:
        return
    base = title.split(" · 姿势裂变")[0].strip()
    if not base:
        return
    others = [item for item in db.scalars(select(WardrobeLook)).all() if item.id != row.id]
    matched = [item for item in others if (item.title or "") == base]
    if not matched:
        matched = [item for item in others if "姿势裂变" not in (item.title or "") and (item.title or "").startswith(base)]
    matched.sort(key=lambda item: item.id)
    if not matched:
        return
    src = look_dir(matched[-1].id) / "look.png"
    if src.is_file():
        write_bytes(folder / "source.png", src.read_bytes())


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


def _style_line(name: str, desc: dict[str, str] | None = None) -> str:
    if not name and not desc:
        return ""
    bits = []
    if desc:
        if desc.get("lighting"):
            bits.append(f"光线要{desc['lighting']}")
        if desc.get("scene"):
            bits.append(f"场景要{desc['scene']}")
        if desc.get("pose"):
            bits.append(f"姿势要{desc['pose']}")
        if desc.get("framing"):
            bits.append(f"构图要{desc['framing']}")
    detail = "；".join(bits)
    label = f"「{name}」" if name else ""
    return (
        f"拍摄风格按{label}只学光线、场景、姿势和构图。"
        + (detail + "。" if detail else "")
        + "白棚就白棚，平光就平光，半身就半身。"
        "禁止自己加房间、窗影、家具、书架。"
        "不要出现 logo 和文字。"
    )


def _single_shot() -> str:
    return "只输出一张完整照片，一个人，一个场景。不要三连图、分栏、拼图、网格、四宫格。"


POSE_VARIANTS = [
    "换成站立姿势：正面或微侧，一只手自然垂下或轻轻插口袋。姿势必须和原图明显不同。",
    "换成走动或回眸姿势：迈一小步，或身体转向一侧看向别处。姿势必须和原图明显不同。",
    "换成坐下或倚靠姿势：坐在合适的位置，或轻轻靠一下。姿势必须和原图明显不同。",
]


def _pose_vary_prompt(pose: str) -> str:
    return (
        "以这张图为唯一参考，拍一张真实时尚照片。"
        "同一个人、同一张脸、同一发型、同一套衣服、同一光线和同一场景。"
        "只改姿势，不要改衣服颜色、版型和细节，不要换人。"
        f"{pose}"
        + _single_shot()
        + "不要文字、水印、logo。"
    )


def _scene_prompt(scene: str) -> str:
    return (
        "以这张图为唯一参考，拍一张真实时尚照片。"
        "同一个人、同一张脸、同一发型、同一套衣服、同一个姿势。"
        f"只把场景和背景换成：{scene}。"
        "不要改衣服颜色、版型和细节，不要换人。"
        + _single_shot()
        + "不要文字、水印、logo。"
    )


def _modeled_prompt(item: dict[str, Any], style_name: str = "", desc: dict[str, str] | None = None) -> str:
    name = item.get("name") or "这件衣服"
    extra = _style_line(style_name, desc)
    return (
        "用第一张图的人，穿上第二张图那件衣服，拍一张真实的时尚照片。"
        f"人脸、发型、年龄、身材要像第一张；衣服要完全是第二张这件{name}，颜色和细节不能改。"
        f"{extra}"
        f"{_single_shot()}"
        "衣服要完整露出来。不要文字、水印。"
    )


def _outfit_prompt(clothes: list[dict[str, Any]], style_name: str = "", desc: dict[str, str] | None = None) -> str:
    lines = []
    tops = 0
    for offset, item in enumerate(clothes):
        part = PART_LABELS.get(item.get("part") or "", "衣服")
        name = item.get("name") or "衣服"
        lines.append(f"第{2 + offset}张图是{part}「{name}」，必须按这张图原样穿上，颜色和细节不能改。")
        if item.get("part") in ("upperbody", "wholebody_up"):
            tops += 1
    extra = _style_line(style_name, desc)
    layer = "上装有两件或以上时必须叠穿，内搭和外衣都要看得见，禁止合成一件，也不能只留一件。" if tops >= 2 else ""
    return (
        "用第一张图的人，同时穿上每张衣服图里的衣服，拍一套完整造型。"
        + "".join(lines)
        + "选了几件就要穿几件，一件都不能少，也不能把两件合成一件。"
        + layer
        + extra
        + _single_shot()
        + "人脸要像第一张。不要文字、水印、logo。"
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
    files = list_style_files(row.id)[:1]
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


@router.post("/wardrobe/suggest")
def suggest_looks(db: Session = Depends(get_db)):
    """看本人照片，从衣橱里给这个人出 2 套搭配方案，先不生图。"""

    ref = reference_path()
    if not ref.is_file():
        return fail("请先上传一张自己的照片")
    rows = db.scalars(select(WardrobeItem).order_by(WardrobeItem.id.desc())).all()
    closet: list[dict[str, Any]] = []
    for row in rows:
        if not (item_dir(row.id) / "cutout.png").is_file():
            continue
        closet.append(
            {
                "id": row.id,
                "name": row.name or "衣服",
                "part": row.part or "upperbody",
                "color": row.color or "",
                "tags": json.loads(row.tags or "[]"),
            }
        )
    tops = [item for item in closet if item["part"] in ("upperbody", "wholebody_up")]
    bottoms = [item for item in closet if item["part"] == "lowerbody"]
    if len(closet) < 2 or not tops or not bottoms:
        return fail("衣橱里至少要有一件上装和一件下装")
    try:
        outfits = suggest_outfits(ref.read_bytes(), closet)
    except ValueError as exc:
        return fail(str(exc))
    valid = {item["id"] for item in closet}
    cleaned: list[dict[str, Any]] = []
    for outfit in outfits:
        ids = [item_id for item_id in outfit.get("item_ids") or [] if item_id in valid][:3]
        if len(ids) < 2:
            continue
        items = [db.get(WardrobeItem, item_id) for item_id in ids]
        cleaned.append(
            {
                "item_ids": ids,
                "reason": outfit.get("reason") or "",
                "items": [_item_dict(row) for row in items if row is not None],
            }
        )
    if not cleaned:
        return fail("没有给出能用的搭配，请再试一次")
    return ok({"items": cleaned[:2]})


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


@router.put("/wardrobe/items/{item_id}")
def update_item(item_id: int, body: ItemPatchIn, db: Session = Depends(get_db)):
    """改衣服分类或名称，用来纠正识别错误。"""

    row = db.get(WardrobeItem, item_id)
    if row is None:
        return fail("没有这件衣服")
    if body.part:
        if body.part not in PART_LABELS:
            return fail("没有这个分类")
        row.part = body.part
    title = (body.name or "").strip()
    if title:
        row.name = title[:200]
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
            size="1024x1024",
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
    for row in rows:
        _backfill_look_style(row, db)
        _backfill_look_source(row, db)
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
    style_desc: dict[str, str] = {}
    if style_bytes:
        try:
            style_desc = describe_style(style_bytes[0])
        except Exception:
            style_desc = {}
    images = [ref.read_bytes()]
    clothes: list[dict[str, Any]] = []
    for row in rows[:3]:
        cutout = item_dir(row.id) / "cutout.png"
        if not cutout.is_file():
            return fail(f"{row.name} 还没有单件图")
        images.append(cutout.read_bytes())
        clothes.append({"name": row.name, "part": row.part})
    names = [item["name"] for item in clothes]
    if len(clothes) == 1:
        prompt = _modeled_prompt({"name": names[0]}, style_name, style_desc)
    else:
        prompt = _outfit_prompt(clothes, style_name, style_desc)
    try:
        picture, ratio, quality = _edit_look(prompt, images, body.ratio, body.quality)
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
    save_look_prompt(row.id, prompt)
    save_look_image_opts(row.id, ratio, quality)
    active = _active_style(db)
    if active is not None:
        copy_style_into_look(row.id, active.id, style_name or active.name or "")
    db.commit()
    db.refresh(row)
    return ok(_look_dict(row))


def _write_look(
    db: Session,
    picture: bytes,
    title: str,
    item_ids: list[int],
    source_id: int = 0,
    source_bytes: bytes = b"",
    prompt: str = "",
    ratio: str = "",
    quality: str = "",
) -> WardrobeLook:
    row = WardrobeLook(title=title[:200], item_ids=json.dumps(item_ids), created_at=datetime.utcnow())
    db.add(row)
    db.flush()
    write_bytes(look_dir(row.id) / "look.png", picture)
    if source_bytes:
        write_bytes(look_dir(row.id) / "source.png", source_bytes)
    save_look_prompt(row.id, prompt)
    if ratio or quality:
        save_look_image_opts(row.id, ratio, quality)
    if source_id:
        copy_look_style(source_id, row.id)
    return row


@router.post("/wardrobe/looks/vary")
async def vary_look(
    look_id: int = Form(0),
    count: int = Form(2),
    ratio: str = Form(""),
    quality: str = Form(""),
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    """从现有搭配或上传图做姿势裂变，张数 1～3。"""

    source: WardrobeLook | None = None
    raw = b""
    if look_id:
        source = db.get(WardrobeLook, look_id)
        if source is None:
            return fail("没有这套搭配")
        path = look_dir(look_id) / "look.png"
        if not path.is_file():
            return fail("这套搭配没有效果图")
        raw = path.read_bytes()
    elif file is not None:
        raw = await file.read()
        if not raw:
            return fail("请先选一张图")
        try:
            raw = to_png(raw)
        except Exception:
            return fail("这张图打不开")
    else:
        return fail("请先选一套搭配，或上传一张图")

    base = (source.title if source else "姿势裂变").split(" · 姿势裂变")[0].strip() or "姿势裂变"
    title = f"{base} · 姿势裂变"
    ids = json.loads(source.item_ids or "[]") if source else []
    created: list[WardrobeLook] = []
    last_error = ""
    times = max(1, min(3, int(count or 2)))
    for pose in POSE_VARIANTS[:times]:
        prompt = _pose_vary_prompt(pose)
        try:
            picture, used_ratio, used_quality = _edit_look(prompt, [raw], ratio, quality, look_id)
        except ValueError as exc:
            last_error = str(exc)
            continue
        created.append(
            _write_look(db, picture, title, ids, source.id if source else 0, raw, prompt, used_ratio, used_quality)
        )
    if not created:
        return fail(last_error or "姿势裂变失败")
    db.commit()
    for row in created:
        db.refresh(row)
    return ok({"items": [_look_dict(row) for row in created]})


@router.post("/wardrobe/looks/{look_id}/remake")
def remake_look(look_id: int, body: LookPromptIn, db: Session = Depends(get_db)):
    """按改过的提示词重做这一套，原图留下来做对比。"""

    prompt = (body.prompt or "").strip()
    if not prompt:
        return fail("请先写提示词")
    row = db.get(WardrobeLook, look_id)
    if row is None:
        return fail("没有这套搭配")
    folder = look_dir(look_id)
    current = folder / "look.png"
    source = folder / "source.png"
    images: list[bytes] = []
    if source.is_file():
        images = [source.read_bytes()]
    else:
        ids = [int(item) for item in json.loads(row.item_ids or "[]")]
        ref = reference_path()
        if ids and ref.is_file():
            images = [ref.read_bytes()]
            for item_id in ids[:3]:
                cutout = item_dir(item_id) / "cutout.png"
                if not cutout.is_file():
                    return fail("有衣服还没有单件图")
                images.append(cutout.read_bytes())
        elif current.is_file():
            images = [current.read_bytes()]
        else:
            return fail("没有参考图，没法重做")
    if current.is_file() and not source.is_file():
        write_bytes(source, current.read_bytes())
    try:
        picture, ratio, quality = _edit_look(prompt, images, body.ratio, body.quality, look_id)
    except ValueError as exc:
        return fail(str(exc))
    write_bytes(current, picture)
    save_look_prompt(look_id, prompt)
    save_look_image_opts(look_id, ratio, quality)
    return ok(_look_dict(row))


@router.post("/wardrobe/looks/scene")
def change_scene(body: SceneIn, db: Session = Depends(get_db)):
    """人、衣服、姿势不变，只换场景。"""

    scene = (body.scene or "").strip()[:80]
    if not scene:
        return fail("请先写场景")
    source = db.get(WardrobeLook, body.look_id)
    if source is None:
        return fail("没有这套搭配")
    path = look_dir(source.id) / "look.png"
    if not path.is_file():
        return fail("这套搭配没有效果图")
    raw = path.read_bytes()
    prompt = _scene_prompt(scene)
    try:
        picture, ratio, quality = _edit_look(prompt, [raw], body.ratio, body.quality, source.id)
    except ValueError as exc:
        return fail(str(exc))
    base = (source.title or "搭配").split(" · 换场景")[0].strip() or "搭配"
    title = f"{base} · {scene}"[:200]
    ids = json.loads(source.item_ids or "[]")
    row = _write_look(db, picture, title, ids, source.id, raw, prompt, ratio, quality)
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
    folder = look_dir(look_id)
    for child in folder.glob("*"):
        if child.is_file():
            child.unlink()
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
    path = read_look_file(look_id, name)
    if path is None:
        return fail("没有这张图")
    return FileResponse(path)


@router.get("/wardrobe/files/styles/{style_id}/{name}")
def file_style(style_id: int, name: str):
    path = read_style_file(style_id, name)
    if path is None:
        return fail("没有这张图")
    return FileResponse(path)
