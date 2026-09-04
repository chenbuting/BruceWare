"""识图：读抽出图上的字。默认关，由库规则打开。不改衣橱。"""

from __future__ import annotations

import base64
import io

from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ai import chat_complete, llm_public
from app.kb.assets import OCR_SKIP
from app.kb.models import KbAsset, KbDocument
from app.kb.store import abs_path

_PROMPT = "看这张图。写出图上能看清的字，并一句话说这是什么。看不清的不要编。只返回纯文本，不要标题。"


def _for_vision(data: bytes) -> tuple[bytes, str]:
    """识别前先压小，少超时。"""

    image = Image.open(io.BytesIO(data)).convert("RGB")
    image.thumbnail((1024, 1024))
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=80)
    return buf.getvalue(), "image/jpeg"


def read_image_text(data: bytes) -> str:
    """认一张图，返回短文本。"""

    preview, mime = _for_vision(data)
    encoded = base64.b64encode(preview).decode("ascii")
    text = chat_complete(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}},
                ],
            }
        ],
        timeout=35,
    )
    return (text or "").strip()[:400]


def _pending(db: Session, document_id: int) -> list[KbAsset]:
    rows = db.scalars(
        select(KbAsset).where(KbAsset.document_id == document_id).order_by(KbAsset.sort_order.asc(), KbAsset.id.asc())
    ).all()
    return [row for row in rows if not (row.ocr_text or "").strip()]


def pending_vision_count(db: Session, document_id: int) -> int:
    """还没认过的图有几张。"""

    return len(_pending(db, document_id))


def recognize_one_asset(row: KbDocument, item: KbAsset) -> None:
    """认一张图，马上写进 ocr_text。失败记下，方便一张一张填。"""

    try:
        path = abs_path(row.library_id, item.rel_path)
        text = read_image_text(path.read_bytes())
    except Exception:
        item.ocr_text = OCR_SKIP
        return
    item.ocr_text = text or OCR_SKIP


def recognize_assets(db: Session, row: KbDocument, limit: int) -> int:
    """认这份资料里还没识过的图。失败的记下，下次不再重试。返回认了几张。"""

    if limit <= 0 or not llm_public().get("has_key"):
        return 0
    pending = _pending(db, row.id)[:limit]
    used = 0
    extras: list[str] = []
    for item in pending:
        used += 1
        try:
            path = abs_path(row.library_id, item.rel_path)
            text = read_image_text(path.read_bytes())
        except Exception:
            item.ocr_text = OCR_SKIP
            continue
        if not text:
            item.ocr_text = OCR_SKIP
            continue
        item.ocr_text = text
        extras.append(text)
    extra = " ".join(part for part in extras if part and part not in (row.search_text or ""))
    if extra:
        row.search_text = ((row.search_text or "") + " " + extra).strip()[:20000]
    return used
