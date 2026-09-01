"""识别照片里的衣服，并按框裁图。"""

from __future__ import annotations

import base64
import io
import json
import re
from typing import Any

from PIL import Image

from app.core.ai import chat_complete

PARTS = ("upperbody", "wholebody_up", "lowerbody", "accessories_up", "shoes")
ANALYZE_PROMPT = """看这张照片，找出每一件真正能进衣橱的衣服（上衣、外套、裤子/裙子、鞋、配饰）。
不要身体、背景、家具。
只返回 JSON，不要其它文字：
{"items":[{"name":"简洁中文名","part":"upperbody|wholebody_up|lowerbody|accessories_up|shoes","color":"#112233","secondaryColor":null,"tags":["面料或细节"],"boundingBox":{"x":0,"y":0,"width":100,"height":100}}]}
boundingBox 用 0-1000 的整数，x/y 是左上角。一张图最多 8 件。"""


def _for_vision(data: bytes) -> tuple[bytes, str]:
    """识别前先压成较小的 JPEG，避免中转站读超时。"""
    image = Image.open(io.BytesIO(data)).convert("RGB")
    image.thumbnail((1024, 1024))
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=80)
    return buf.getvalue(), "image/jpeg"


def analyze_photo(data: bytes, mime: str = "image/jpeg") -> list[dict[str, Any]]:
    preview, preview_mime = _for_vision(data)
    encoded = base64.b64encode(preview).decode("ascii")
    text = chat_complete(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": ANALYZE_PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:{preview_mime};base64,{encoded}"}},
                ],
            }
        ],
        timeout=180,
    )
    payload = _parse_json(text)
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise ValueError("没有识别出衣服")
    return [_normalize(item) for item in items if isinstance(item, dict)][:8]


def crop_box(data: bytes, box: dict[str, Any]) -> bytes:
    image = Image.open(io.BytesIO(data)).convert("RGB")
    width, height = image.size
    x = _num(box.get("x"), 0)
    y = _num(box.get("y"), 0)
    w = max(1, _num(box.get("width"), 200))
    h = max(1, _num(box.get("height"), 200))
    left = int(width * x / 1000)
    top = int(height * y / 1000)
    right = int(width * (x + w) / 1000)
    bottom = int(height * (y + h) / 1000)
    pad = max(12, int(max(right - left, bottom - top) * 0.08))
    left = max(0, left - pad)
    top = max(0, top - pad)
    right = min(width, right + pad)
    bottom = min(height, bottom + pad)
    cropped = image.crop((left, top, max(left + 1, right), max(top + 1, bottom)))
    buf = io.BytesIO()
    cropped.save(buf, format="PNG")
    return buf.getvalue()


def to_png(data: bytes) -> bytes:
    """把上传的图转成 PNG，方便直接当单件图存。"""
    image = Image.open(io.BytesIO(data))
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def remove_chroma(data: bytes) -> bytes:
    image = Image.open(io.BytesIO(data)).convert("RGBA")
    pixels = list(image.getdata())
    out = []
    for r, g, b, a in pixels:
        if (g > 170 and r < 130 and b < 130) or (b > 170 and r > 170 and g < 130):
            out.append((0, 0, 0, 0))
        else:
            out.append((r, g, b, a))
    image.putdata(out)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _parse_json(text: str) -> Any:
    raw = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]+?)```", raw)
    if match:
        raw = match.group(1).strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        raw = raw[start : end + 1]
    return json.loads(raw)


def _num(value: Any, fallback: int) -> int:
    try:
        return max(0, min(1000, int(value)))
    except Exception:
        return fallback


def _normalize(item: dict[str, Any]) -> dict[str, Any]:
    part = str(item.get("part") or "upperbody")
    if part not in PARTS:
        part = "upperbody"
    color = str(item.get("color") or "").strip()
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", color):
        color = ""
    secondary = str(item.get("secondaryColor") or item.get("secondary_color") or "").strip()
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", secondary):
        secondary = ""
    tags = item.get("tags") if isinstance(item.get("tags"), list) else []
    return {
        "name": str(item.get("name") or "衣服")[:80],
        "part": part,
        "color": color.lower(),
        "secondaryColor": secondary.lower(),
        "tags": [str(tag).strip()[:20] for tag in tags if str(tag).strip()][:6],
        "boundingBox": {
            "x": _num((item.get("boundingBox") or {}).get("x") if isinstance(item.get("boundingBox"), dict) else 0, 0),
            "y": _num((item.get("boundingBox") or {}).get("y") if isinstance(item.get("boundingBox"), dict) else 0, 0),
            "width": max(1, _num((item.get("boundingBox") or {}).get("width") if isinstance(item.get("boundingBox"), dict) else 200, 200)),
            "height": max(1, _num((item.get("boundingBox") or {}).get("height") if isinstance(item.get("boundingBox"), dict) else 200, 200)),
        },
    }
