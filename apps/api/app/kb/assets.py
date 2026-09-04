"""从资料里抽图并落盘。识图默认关，这刀只抽图、给出处。"""

from __future__ import annotations

import io
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.kb.extract import extract_search_text
from app.kb.models import KbAsset, KbDocument
from app.kb.search import search_terms
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


def score_asset(question: str, item: KbAsset) -> float:
    """问句和图上的字、图名有多贴。"""

    blob = f"{item.alt_text or ''} {ocr_for_search(item.ocr_text or '')}".lower()
    q = question.strip().lower()
    if not q or not blob.strip():
        return 0.0
    if q in blob:
        return 2.0
    terms = search_terms(question)
    if not terms:
        return 0.0
    hit = sum(1 for term in terms if term in blob)
    return hit / len(terms) if hit else 0.0


def assets_for_docs(db: Session, doc_ids: list[int], question: str = "", per_doc: int = 4) -> dict[int, list[KbAsset]]:
    """提问出处用：优先带和问句对得上的图，每份最多几张。"""

    if not doc_ids:
        return {}
    rows = db.scalars(
        select(KbAsset).where(KbAsset.document_id.in_(doc_ids)).order_by(KbAsset.sort_order.asc(), KbAsset.id.asc())
    ).all()
    grouped: dict[int, list[KbAsset]] = {}
    for row in rows:
        grouped.setdefault(row.document_id, []).append(row)
    picked: dict[int, list[KbAsset]] = {}
    for doc_id, items in grouped.items():
        scored = [(score_asset(question, item), item) for item in items]
        scored.sort(key=lambda pair: (-pair[0], pair[1].sort_order or 0, pair[1].id or 0))
        matched = [item for score, item in scored if score > 0]
        picked[doc_id] = matched[:per_doc]
    return picked


def asset_dict(row: KbAsset) -> dict:
    return {
        "id": row.id,
        "alt": row.alt_text or "",
        "page": row.page or 0,
        "url": f"/api/v1/kb/assets/{row.id}/file",
    }


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
    data["ocr_text"] = ocr_for_edit(row.ocr_text or "")
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
