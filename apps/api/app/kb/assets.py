"""从资料里抽图并落盘。识图默认关，这刀只抽图、给出处。"""

from __future__ import annotations

import io
import json
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ai import chat_complete, llm_public
from app.kb.extract import extract_search_text
from app.kb.models import KbAsset, KbDocument
from app.kb.store import abs_path, kind_of, remove_file, write_bytes

OCR_SKIP = "-"

_MIN_SIDE = 80


def _extra(row: KbDocument) -> dict:
    raw = (row.extra or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _set_extra(row: KbDocument, key: str, value) -> None:
    data = _extra(row)
    data[key] = value
    row.extra = json.dumps(data, ensure_ascii=False)


def already_extracted(row: KbDocument) -> bool:
    """这份资料是不是已经抽过图。提问前用来跳过读盘。"""

    return bool(_extra(row).get("assets_done"))


def _usable_image(data: bytes) -> bytes | None:
    """太小的图标丢掉。能开就转成 jpeg，打不开但像图片就原样留下。"""

    if not data or len(data) < 80:
        return None
    try:
        from PIL import Image

        image = Image.open(io.BytesIO(data))
        image = image.convert("RGB")
        if min(image.size) < _MIN_SIDE:
            return None
        buf = io.BytesIO()
        image.save(buf, format="JPEG", quality=82)
        return buf.getvalue()
    except Exception:
        return data if len(data) > 800 else None


def _from_pdf(data: bytes) -> list[tuple[int, bytes]]:
    try:
        from pypdf import PdfReader
    except ImportError:
        return []
    found: list[tuple[int, bytes]] = []
    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception:
        return []
    for page_no, page in enumerate(reader.pages, start=1):
        try:
            images = page.images
        except Exception:
            continue
        for item in images:
            raw = getattr(item, "data", None)
            if not raw:
                continue
            usable = _usable_image(raw)
            if usable:
                found.append((page_no, usable))
    return found


def _from_docx(data: bytes) -> list[tuple[int, bytes]]:
    try:
        from docx import Document
    except ImportError:
        return []
    found: list[tuple[int, bytes]] = []
    try:
        doc = Document(io.BytesIO(data))
        rels = doc.part.rels.values()
    except Exception:
        return []
    for rel in rels:
        try:
            if "image" not in str(getattr(rel, "reltype", "")):
                continue
            raw = rel.target_part.blob
        except Exception:
            continue
        usable = _usable_image(raw)
        if usable:
            found.append((0, usable))
    return found


def extract_images(file_name: str, data: bytes) -> list[tuple[int, bytes]]:
    """按后缀抽图。独立图片返回一张；抽不到返回空。"""

    suffix = Path(file_name or "").suffix.lower()
    kind = kind_of(file_name)
    if kind == "image":
        usable = _usable_image(data)
        return [(0, usable)] if usable else []
    if suffix == ".pdf":
        return _from_pdf(data)
    if suffix == ".docx":
        return _from_docx(data)
    return []


def clear_assets(db: Session, row: KbDocument) -> None:
    """删图记录。抽出来的另存文件也删；和原件同一路径的不在这里删原件。"""

    items = db.scalars(select(KbAsset).where(KbAsset.document_id == row.id)).all()
    main = (row.rel_path or "").replace("\\", "/")
    for item in items:
        rel = (item.rel_path or "").replace("\\", "/")
        if rel and rel != main:
            remove_file(row.library_id, rel)
    db.execute(KbAsset.__table__.delete().where(KbAsset.document_id == row.id))


def save_extracted_images(db: Session, row: KbDocument, data: bytes) -> list[str]:
    """抽图落盘。已抽过的只补后面缺的，已有的图和识图文字不动。"""

    existing = list(
        db.scalars(
            select(KbAsset).where(KbAsset.document_id == row.id).order_by(KbAsset.sort_order.asc(), KbAsset.id.asc())
        ).all()
    )
    alts = [item.alt_text for item in existing if item.alt_text]
    kind = row.kind or kind_of(row.file_name)
    if kind == "image" and row.rel_path:
        if not existing:
            alt = row.title or row.file_name or "图片"
            db.add(
                KbAsset(
                    library_id=row.library_id,
                    document_id=row.id,
                    rel_path=row.rel_path,
                    page=0,
                    sort_order=0,
                    alt_text=alt,
                )
            )
            alts.append(alt)
        _set_extra(row, "assets_done", True)
        return alts

    pictures = extract_images(row.file_name, data)
    start = len(existing)
    if start >= len(pictures):
        _set_extra(row, "assets_done", True)
        return alts
    for offset, (page, blob) in enumerate(pictures[start:]):
        index = start + offset + 1
        alt = f"第{page}页图{index}" if page else f"图{index}"
        rel = f"assets/{row.id}/{index:02d}.jpg"
        write_bytes(row.library_id, rel, blob)
        db.add(
            KbAsset(
                library_id=row.library_id,
                document_id=row.id,
                rel_path=rel,
                page=page,
                sort_order=index,
                alt_text=alt,
            )
        )
        alts.append(alt)
    _set_extra(row, "assets_done", True)
    return alts


def append_asset_alts(row: KbDocument, alts: list[str]) -> None:
    """图名写进检索正文，没识图也能按「第几页图」搜到。"""

    extra = " ".join(item for item in alts if item and item not in (row.search_text or ""))
    if not extra:
        return
    row.search_text = ((row.search_text or "") + " " + extra).strip()[:20000]


def _asset_caption(item: KbAsset, limit: int = 240) -> str:
    """给选图模型看的一小段：图名 + 识图文字。"""

    name = (item.alt_text or "").strip()
    text = re.sub(r"\s+", " ", ocr_for_search(item.ocr_text or "")).strip()
    if len(text) > limit:
        text = text[:limit]
    return f"{name} {text}".strip()


def _parse_picked_ids(text: str, allowed: set[int]) -> list[int]:
    """只收下模型点名的图编号，别的数字丢掉。"""

    raw = (text or "").strip()
    if not raw or raw in {"无", "没有", "none", "[]"}:
        return []
    found: list[int] = []
    for match in re.findall(r"A(\d+)", raw, flags=re.I):
        num = int(match)
        if num in allowed and num not in found:
            found.append(num)
    if found:
        return found
    for match in re.findall(r"\d+", raw):
        num = int(match)
        if num in allowed and num not in found:
            found.append(num)
    return found


def pick_assets_by_meaning(question: str, items: list[KbAsset]) -> list[KbAsset]:
    """先看用户要不要图，再按意思挑。没要图就不带。"""

    q = question.strip()
    if not q or not items:
        return []
    if not llm_public().get("has_key"):
        return []
    by_id = {item.id: item for item in items if item.id}
    if not by_id:
        return []
    lines = []
    for item in items:
        if not item.id:
            continue
        caption = _asset_caption(item)
        if not caption:
            continue
        lines.append(f"[A{item.id}] {caption}")
    if not lines:
        return []
    prompt = (
        "先理解用户这句是不是在要图、要原件、要看某份证件。\n"
        "只问事实、只要文字答案、没有要看图或原件的意思：输出无。不要为了当证据而配图。\n"
        "确实在要图：再按意思选真正符合的图。标题不必一字不差。\n"
        "一句里又要图又要问数：只选要图的那部分，问事实的部分不配图。\n"
        "用户可能要好几样。有一样选一样，缺的不要拿别的证件凑。\n"
        "只是碰巧出现了相近的字、但不是同一类东西，不要选。\n"
        "不确定就不要选。\n"
        "只输出符合的编号，例如：A11,A4\n"
        "一个都没有就输出：无\n"
        "不要解释。\n\n"
        f"用户问题：{q}\n\n"
        + "\n".join(lines)
    )
    try:
        answer = chat_complete(
            [
                {"role": "system", "content": "你先判断用户要不要图，再决定选哪些。不回答问题本身。"},
                {"role": "user", "content": prompt},
            ],
            timeout=60,
        )
    except Exception:
        return []
    picked = []
    for asset_id in _parse_picked_ids(answer, set(by_id)):
        picked.append(by_id[asset_id])
    return picked


def asset_notes_for_ask(items: list[KbAsset], limit: int = 500) -> str:
    """命中图的图意和字，给回答当原文。"""

    lines = []
    for item in items:
        text = ocr_for_search(item.ocr_text or "")
        if not text:
            continue
        if len(text) > limit:
            text = text[:limit]
        name = (item.alt_text or "图").strip()
        lines.append(f"【{name}】{text}")
    return "\n".join(lines)


def assets_for_docs(db: Session, doc_ids: list[int], question: str = "") -> dict[int, list[KbAsset]]:
    """提问出处用：按意思带对得上的图。没认过字的不带。"""

    if not doc_ids:
        return {}
    rows = db.scalars(
        select(KbAsset).where(KbAsset.document_id.in_(doc_ids)).order_by(KbAsset.sort_order.asc(), KbAsset.id.asc())
    ).all()
    grouped: dict[int, list[KbAsset]] = {}
    for row in rows:
        grouped.setdefault(row.document_id, []).append(row)
    candidates = [item for item in rows if ocr_for_search(item.ocr_text or "")]
    chosen = pick_assets_by_meaning(question, candidates)
    picked = {doc_id: [] for doc_id in grouped}
    for item in chosen:
        picked.setdefault(item.document_id, []).append(item)
    return picked


def asset_dict(row: KbAsset) -> dict:
    return {
        "id": row.id,
        "alt": row.alt_text or "",
        "page": row.page or 0,
        "url": f"/api/v1/kb/assets/{row.id}/file",
    }


def parse_asset_note(text: str) -> dict[str, str]:
    """把存着的一段拆成图意、关键词、图上的字。旧数据整段落到字。"""

    value = (text or "").strip()
    empty = {"caption": "", "keywords": "", "words": ""}
    if not value or value == OCR_SKIP:
        return empty
    caption_m = re.search(r"图意[：:]\s*(.*?)(?=\n关键词[：:]|\n图上的字[：:]|$)", value, flags=re.S)
    keyword_m = re.search(r"关键词[：:]\s*(.*?)(?=\n图意[：:]|\n图上的字[：:]|$)", value, flags=re.S)
    words_m = re.search(r"图上的字[：:]\s*(.*)\Z", value, flags=re.S)
    if not (caption_m or keyword_m or words_m):
        return {"caption": "", "keywords": "", "words": value}
    words = (words_m.group(1) if words_m else "").strip()
    if words in {"无", "没有"}:
        words = ""
    return {
        "caption": (caption_m.group(1) if caption_m else "").strip()[:200],
        "keywords": re.sub(r"\s+", " ", (keyword_m.group(1) if keyword_m else "").strip())[:200],
        "words": words[:1500],
    }


def pack_asset_note(caption: str, keywords: str, words: str) -> str:
    """三块写回一段，检索和提问仍读这一段。"""

    cap = (caption or "").strip()
    keys = (keywords or "").strip()
    body = (words or "").strip()
    if body in {"无", "没有"}:
        body = ""
    if not cap and not keys and not body:
        return ""
    lines = []
    if cap:
        lines.append(f"图意：{cap}")
    if keys:
        lines.append(f"关键词：{keys}")
    lines.append(f"图上的字：{body or '无'}")
    return "\n".join(lines)


def normalize_asset_note(text: str) -> str:
    """识图结果整理成统一三段。"""

    parts = parse_asset_note(text)
    return pack_asset_note(parts["caption"], parts["keywords"], parts["words"])


def ocr_for_search(text: str) -> str:
    """空的或失败标记不进检索。"""

    value = (text or "").strip()
    if not value or value == OCR_SKIP:
        return ""
    return value


def ocr_for_edit(text: str) -> str:
    """给预览改字用。失败标记显示成空。"""

    return ocr_for_search(text)


def asset_edit_dict(row: KbAsset) -> dict:
    data = asset_dict(row)
    parts = parse_asset_note(ocr_for_edit(row.ocr_text or ""))
    data["caption"] = parts["caption"]
    data["keywords"] = parts["keywords"]
    data["ocr_text"] = parts["words"]
    return data


def list_doc_assets(db: Session, document_id: int) -> list[KbAsset]:
    return list(
        db.scalars(
            select(KbAsset).where(KbAsset.document_id == document_id).order_by(KbAsset.sort_order.asc(), KbAsset.id.asc())
        ).all()
    )


def rebuild_search_text(db: Session, row: KbDocument) -> None:
    """按原文 + 图名 + 识图文字重拼检索正文。"""

    body = ""
    try:
        data = abs_path(row.library_id, row.rel_path).read_bytes()
        body = extract_search_text(row.file_name, data)
    except (ValueError, OSError):
        body = ""
    parts = [body]
    for item in list_doc_assets(db, row.id):
        if item.alt_text:
            parts.append(item.alt_text)
        extra = ocr_for_search(item.ocr_text or "")
        if extra:
            parts.append(extra)
    row.search_text = " ".join(part for part in parts if part).strip()[:20000]
