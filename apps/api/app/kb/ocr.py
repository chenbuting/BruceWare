"""本地 OCR：只抄图上的字，不走对话模型。"""

from __future__ import annotations

import io

from PIL import Image

_OCR = None
_KIND = ""


def ensure_ocr() -> None:
    """第一次用时加载。没装组件就说清楚。"""

    _engine()


def _engine():
    global _OCR, _KIND
    if _OCR is not None:
        return _OCR, _KIND
    try:
        from rapidocr_onnxruntime import RapidOCR

        _OCR = RapidOCR()
        _KIND = "legacy"
        return _OCR, _KIND
    except ImportError:
        pass
    try:
        from rapidocr import RapidOCR

        _OCR = RapidOCR()
        _KIND = "new"
        return _OCR, _KIND
    except ImportError as exc:
        raise ValueError("还没装 OCR 组件。请在 apps/api 目录执行：pip install rapidocr-onnxruntime") from exc


def _lines_of(result, kind: str) -> list[str]:
    if result is None:
        return []
    if kind == "new":
        texts = getattr(result, "txts", None)
        if texts:
            return [str(item).strip() for item in texts if str(item).strip()]
        return []
    rows, _elapsed = result if isinstance(result, tuple) else (result, None)
    if not rows:
        return []
    found = []
    for item in rows:
        if isinstance(item, (list, tuple)) and len(item) > 1:
            text = str(item[1]).strip()
            if text:
                found.append(text)
    return found


def read_ocr_text(data: bytes) -> str:
    """认一张图上的字。"""

    if not data:
        return ""
    image = Image.open(io.BytesIO(data)).convert("RGB")
    engine, kind = _engine()
    try:
        import numpy as np

        payload = np.array(image)
    except ImportError:
        payload = image
    result = engine(payload)
    return " ".join(_lines_of(result, kind)).strip()[:400]
